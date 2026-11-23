from __future__ import annotations

import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, WebSocket
from pydantic import BaseModel, Field, field_validator

import db
from db import adb
import skill_check
import character_data as cd
from services.crash_capture import to_json_safe as _crash_to_json_safe

logger = logging.getLogger("hikayat-server")


class ConnectionManager:
    """WebSocket Connection Manager for Multiplayer Lobbies & Live Streaming."""

    def __init__(self):
        self.active_connections: Dict[int, List[Dict[str, Any]]] = {}

    async def connect(self, session_id: int, user_id: int, websocket: WebSocket):
        await websocket.accept()
        try:
            clean_sid = int(session_id)
        except (ValueError, TypeError):
            clean_sid = session_id
        if clean_sid not in self.active_connections:
            self.active_connections[clean_sid] = []
        self.active_connections[clean_sid].append({"ws": websocket, "user_id": user_id})
        logger.info(f"User {user_id} connected to WebSocket session {clean_sid}")
        await self.broadcast_presence(clean_sid)

    def disconnect(self, session_id: int, websocket: WebSocket):
        try:
            clean_sid = int(session_id)
        except (ValueError, TypeError):
            clean_sid = session_id
        if clean_sid in self.active_connections:
            self.active_connections[clean_sid] = [
                c for c in self.active_connections[clean_sid] if c["ws"] != websocket
            ]
            if not self.active_connections[clean_sid]:
                del self.active_connections[clean_sid]

    async def broadcast_presence(self, session_id: int):
        try:
            clean_sid = int(session_id)
        except (ValueError, TypeError):
            clean_sid = session_id
        if clean_sid not in self.active_connections:
            return
        def _load_presence_bundle() -> tuple[list, dict[int, dict]]:
            with db.ReadUnitOfWork():
                sess_members = list(db.get_session_members(clean_sid) or [])
                sess_chars = {
                    int(c["user_id"]): dict(c)
                    for c in (db.get_session_characters(clean_sid) or [])
                    if isinstance(c, dict) and c.get("user_id") is not None
                }
                for uid in sess_members:
                    u_int = int(uid)
                    if u_int not in sess_chars:
                        ch = db.get_character(u_int)
                        if isinstance(ch, dict):
                            sess_chars[u_int] = dict(ch)
                return sess_members, sess_chars

        members, chars_by_uid = await adb(_load_presence_bundle)
        conns = list(self.active_connections.get(clean_sid) or [])
        if not conns:
            return
        connected_uids = [c["user_id"] for c in conns]

        member_profiles = []
        for uid in members:
            c = chars_by_uid.get(int(uid))
            member_profiles.append({
                "user_id": uid,
                "name": c["name"] if c else f"User {uid}",
                "level": c["level"] if c else 1,
                "online": uid in connected_uids
            })

        payload = {
            "type": "PRESENCE_UPDATE",
            "session_id": clean_sid,
            "members": member_profiles
        }
        await self.broadcast(clean_sid, payload)

    async def broadcast(self, session_id: int, message: dict):
        try:
            clean_sid = int(session_id)
        except (ValueError, TypeError):
            clean_sid = session_id
        conns = self.active_connections.get(clean_sid, [])
        if not conns and isinstance(clean_sid, int):
            conns = self.active_connections.get(str(clean_sid), [])
        elif not conns and isinstance(clean_sid, str) and clean_sid.isdigit():
            conns = self.active_connections.get(int(clean_sid), [])
        if not conns:
            return
        safe_message = _to_json_safe(message)
        async def _safe_send(conn):
            lock = conn.setdefault("lock", asyncio.Lock())
            async with lock:
                try:
                    await conn["ws"].send_json(safe_message)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {conn['user_id']}: {e}")
                    self.disconnect(clean_sid, conn["ws"])

        await asyncio.gather(*[_safe_send(c) for c in list(conns)], return_exceptions=True)

    async def send_personal(self, session_id: int, websocket: WebSocket, message: dict) -> None:
        """Send a serialized JSON message to a single socket under its connection lock."""
        try:
            clean_sid = int(session_id)
        except (ValueError, TypeError):
            clean_sid = session_id
        conns = self.active_connections.get(clean_sid, [])
        if not conns and isinstance(clean_sid, int):
            conns = self.active_connections.get(str(clean_sid), [])
        elif not conns and isinstance(clean_sid, str) and clean_sid.isdigit():
            conns = self.active_connections.get(int(clean_sid), [])
        target = next((c for c in list(conns) if c.get("ws") is websocket), None)
        safe_message = _to_json_safe(message)
        if target is None:
            await websocket.send_json(safe_message)
            return
        lock = target.setdefault("lock", asyncio.Lock())
        async with lock:
            try:
                await websocket.send_json(safe_message)
            except Exception as e:
                logger.error(f"Error sending personal WS frame to user {target.get('user_id')}: {e}")
                self.disconnect(clean_sid, target["ws"])


manager = ConnectionManager()


_JSON_SAFE_TRANSIENT_KEYS = frozenset({"_ctx", "_target_turn", "_world_events_snapshot", "_dealt_social_seeds", "_prompt_epoch", "prompt_epoch"})


def _to_json_safe(val, _seen: set[int] | None = None):
    return _crash_to_json_safe(
        val,
        _seen,
        transient_keys=_JSON_SAFE_TRANSIENT_KEYS,
        sanitize_paths=False,
        stringify_unknown=False,
    )


def require_active_session(session: Optional[Dict[str, Any]]) -> None:
    """Raise HTTP 400 if the adventure session is missing or no longer active."""
    if not session or str(session.get("status") or "active").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="This adventure session is no longer active.")


def _serializable_action(action: dict) -> dict:
    """Returns a deep copy of the action dict safe for json.dumps (no raw dataclass objects at any depth)."""
    if not isinstance(action, dict):
        return {}
    return _to_json_safe(action)


def enrich_choices_with_odds(
    choices: list,
    user_id: int,
    session: dict = None,
    *,
    char: dict | None = None,
    user_settings: dict | None = None,
    inv: list | None = None,
) -> list:
    """Enriches scene choices with calculated success_pct, chance, and Discord-matching action icons."""
    from game_engine import (
        get_choice_quest_icon as _get_choice_quest_icon,
        get_choice_skill_emoji as _get_choice_skill_emoji,
        get_choice_emoji as _get_choice_emoji,
    )
    from mechanics.stealth import compute_choice_stealth_odds

    if user_settings is None and user_id:
        user_settings = db.get_settings(user_id)
    if char is None and user_id:
        char = db.get_character(user_id, settings=user_settings)
    if user_settings is None:
        user_settings = db.get_settings(char["user_id"]) if char else {}
    check_mode = (user_settings or {}).get("debug_check_mode", "off")
    if inv is None and char and choices and isinstance(session, dict):
        inv = db.get_inventory(user_id, char=char) or []

    enriched = []
    for c in (choices or []):
        if not isinstance(c, dict):
            continue
        choice_copy = dict(c)
        stat = str(c.get("stat", "STR") or "STR").upper()
        req = c.get("requirement", 5)
        try:
            req_int = int(req) if req is not None else 5
        except (TypeError, ValueError):
            req_int = 5

        if char:
            stat_val = char.get(db.STAT_COLUMN.get(stat, "str_"), 1)
            if stat in ("NONE", "FREE", "ITEM") or req_int <= 0:
                pct = 100
            else:
                stealth_pct = (
                    compute_choice_stealth_odds(
                        session,
                        char,
                        choice_copy,
                        equipped_items=inv,
                        user_id=user_id,
                    )
                    if isinstance(session, dict) and check_mode in ("off", "", None)
                    else None
                )
                if stealth_pct is not None:
                    pct = int(stealth_pct)
                    stat_val = char.get("agi_", stat_val)
                else:
                    rate = skill_check.success_chance(stat_val, req_int, check_mode=check_mode)
                    pct = int(round(rate))
            choice_copy["success_pct"] = pct
            choice_copy["chance"] = pct
            choice_copy["stat_val"] = stat_val

        choice_copy["quest_icon"] = _get_choice_quest_icon(choice_copy)
        choice_copy["skill_emoji"] = _get_choice_skill_emoji(choice_copy)
        choice_copy["emoji"] = _get_choice_emoji(choice_copy)
        enriched.append(choice_copy)
    return enriched


def _parse_status_effects_list(raw_val: Any) -> List[Any]:
    if not raw_val:
        return []
    if isinstance(raw_val, list):
        return raw_val
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return list(raw_val) if isinstance(raw_val, (tuple, set)) else []


def _batch_load_party_characters(
    missing_uids: List[int],
    *,
    session_id: Optional[int] = None,
) -> Dict[int, Dict[str, Any]]:
    return db.batch_load_party_characters(missing_uids, session_id=session_id)


def _format_party_member_entry(
    uid: Any,
    char_data: Dict[str, Any],
    *,
    used_slots: Optional[int] = None,
    capacity: Optional[int] = None,
) -> Dict[str, Any]:
    raw_eff_val = _parse_status_effects_list(char_data.get("status_effects"))
    eff_cap = int(capacity) if capacity is not None else int(cd.inventory_capacity(int(char_data.get("str_", 5) or 5)))
    eff_used = int(used_slots) if used_slots is not None else 0
    return {
        "user_id": uid,
        "character_id": char_data.get("id"),
        "name": char_data.get("name"),
        "char_class": char_data.get("char_class"),
        "level": char_data.get("level", 1),
        "hp": char_data.get("hp", 0),
        "max_hp": char_data.get("max_hp", 0),
        "mp": char_data.get("mp", 0),
        "max_mp": char_data.get("max_mp", 0),
        "gold": char_data.get("gold", 0),
        "used_slots": eff_used,
        "capacity": eff_cap,
        "stats": {
            "str": char_data.get("str_", 1),
            "per": char_data.get("per_", 1),
            "end": char_data.get("end_", 1),
            "cha": char_data.get("cha", 1),
            "int": char_data.get("int_", 1),
            "agi": char_data.get("agi", 1),
            "luk": char_data.get("luk", 1),
        },
        "status_effects": cd.sanitize_status_effects(raw_eff_val),
        "gender": char_data.get("gender"),
        "scenario": char_data.get("scenario"),
    }


def enrich_session_party_members(
    session_dict: Dict[str, Any],
    *,
    preloaded_chars: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Fetches real-time vitals, capacity, and status effects for all human characters in the party."""
    session_id = session_dict.get("id")
    if not session_id:
        return []
    uids = db.get_session_members(session_id) or (
        [session_dict["host_user_id"]] if session_dict.get("host_user_id") else []
    )
    chars_by_uid: Dict[int, Dict[str, Any]] = {
        int(k): v for k, v in (preloaded_chars or {}).items() if k is not None and isinstance(v, dict)
    }
    missing_uids = [int(u) for u in uids if u is not None and int(u) not in chars_by_uid]
    if len(missing_uids) > 1:
        chars_by_uid.update(_batch_load_party_characters(missing_uids, session_id=session_id))

    resolved_chars: List[Tuple[Any, Dict[str, Any]]] = []
    for uid in uids:
        u_int = int(uid)
        c = chars_by_uid[u_int] if u_int in chars_by_uid else db.get_character(uid, session_id=session_id)
        if c:
            resolved_chars.append((uid, c))

    inv_by_cid: Dict[int, List[Dict[str, Any]]] = {}
    if resolved_chars:
        try:
            inv_by_cid = db.get_inventories_for_characters([c for _, c in resolved_chars]) or {}
        except Exception:
            inv_by_cid = {}

    prop_bonus = db.get_session_property_slot_bonus(int(session_id))
    members: List[Dict[str, Any]] = []
    for uid, c in resolved_chars:
        cid = c.get("id")
        c_inv = inv_by_cid.get(int(cid), []) if cid is not None else []
        try:
            u_slots = db.compute_inventory_used_slots(c_inv)
            cap = cd.inventory_capacity(int(c.get("str_", 1) or 1), bonus_slots=prop_bonus)
        except Exception:
            u_slots = len(c_inv)
            cap = cd.inventory_capacity(int(c.get("str_", 5) or 5))
        members.append(_format_party_member_entry(uid, c, used_slots=u_slots, capacity=cap))
    return members


# -----------------------------------------------------------------------------
# Pydantic Request Models
# -----------------------------------------------------------------------------
class GuestAuthRequest(BaseModel):
    guest_name: Optional[str] = "Adventurer"
    display_name: Optional[str] = None


class DiscordAuthRequest(BaseModel):
    user_id_or_name: Optional[str] = None
    discord_id: Optional[str] = None


class CharacterCreateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    user_id: int
    name: str
    char_class: Optional[str] = "Warrior"
    class_name: Optional[str] = None
    class_description: Optional[str] = ""
    gender: Optional[str] = "Male"
    race: Optional[str] = "Human"
    race_description: Optional[str] = ""
    scenario: Optional[str] = "fantasy"
    tags: Optional[list[str] | str] = None
    starting_weapon: Optional[str] = None
    starting_weapon_description: Optional[str] = ""
    starter_loadout: Optional[dict] = None
    str_val: int = Field(1, ge=1, le=10, alias="str")
    per: int = Field(1, ge=1, le=10)
    end: int = Field(1, ge=1, le=10)
    cha: int = Field(1, ge=1, le=10)
    int_val: int = Field(1, ge=1, le=10, alias="int")
    agi: int = Field(1, ge=1, le=10)
    luk: int = Field(1, ge=1, le=10)
    appearance: Optional[dict] = None
    breast_size: Optional[str] = None
    penis_size: Optional[str] = None
    asset_texture: Optional[str] = None
    starting_faction: Optional[str] = None
    origin_mode: Optional[str] = None
    student_grade: Optional[str] = None
    attribute: Optional[str] = None
    combat_archetype: Optional[str] = None
    ability_medium: Optional[str] = None


class CharacterAppearanceUpdateRequest(BaseModel):
    user_id: int
    character_id: Optional[int] = None
    appearance: Optional[dict] = None
    breast_size: Optional[str] = None
    penis_size: Optional[str] = None
    asset_texture: Optional[str] = None



class PreviewGearRequest(BaseModel):
    char_class: Optional[str] = "Warrior"
    class_description: Optional[str] = ""
    scenario: Optional[str] = "fantasy"
    tags: Optional[list[str] | str] = None
    gender: Optional[str] = "Male"
    race: Optional[str] = "Human"
    starting_weapon: Optional[str] = ""
    force_dynamic: Optional[bool] = True
    starting_faction: Optional[str] = None
    origin_mode: Optional[str] = None
    student_grade: Optional[str] = None


class RegenerateGearRequest(BaseModel):
    user_id: int
    starting_faction: Optional[str] = None
    origin_mode: Optional[str] = None
    student_grade: Optional[str] = None


class CharacterSwitchRequest(BaseModel):
    user_id: int
    character_id: int


class SpendStatPointRequest(BaseModel):
    user_id: int
    stat: str


class EquipRequest(BaseModel):
    user_id: int
    item_id: int
    slot: str


class UnequipRequest(BaseModel):
    user_id: int
    slot: str


class ItemDropRequest(BaseModel):
    user_id: int
    item_id: int


class ItemUseRequest(BaseModel):
    user_id: int
    item_id: int
    target_type: Optional[str] = "self"
    target_name: Optional[str] = "self"
    target_user_id: Optional[int] = None
    session_id: Optional[int] = None


class JoinAdventureRequest(BaseModel):
    user_id: int
    join_code: str


class StartAdventureRequest(BaseModel):
    model_config = {"populate_by_name": True}

    user_id: int
    mode: str = "solo"
    scenario: str = "fantasy"
    capacity: int = 1
    party_user_ids: Optional[List[int]] = []
    tags: Optional[List[str]] = []
    char_class: Optional[str] = None
    class_description: Optional[str] = None
    weapon_name: Optional[str] = None
    weapon_description: Optional[str] = None
    starter_loadout: Optional[Dict[str, Any]] = None
    starting_items: Optional[List[Dict[str, Any]]] = None
    str_val: Optional[int] = Field(None, ge=1, le=10, alias="str")
    per: Optional[int] = Field(None, ge=1, le=10)
    end: Optional[int] = Field(None, ge=1, le=10)
    cha: Optional[int] = Field(None, ge=1, le=10)
    int_val: Optional[int] = Field(None, ge=1, le=10, alias="int")
    agi: Optional[int] = Field(None, ge=1, le=10)
    luk: Optional[int] = Field(None, ge=1, le=10)
    breast_size: Optional[str] = None
    penis_size: Optional[str] = None
    asset_texture: Optional[str] = None
    starting_faction: Optional[str] = None
    origin_mode: Optional[str] = None
    student_grade: Optional[str] = None
    attribute: Optional[str] = None
    combat_archetype: Optional[str] = None
    ability_medium: Optional[str] = None
    appearance: Optional[Dict[str, Any]] = None
    slot: Optional[int] = 1
    character_id: Optional[int] = None

    @field_validator("scenario", mode="before")
    @classmethod
    def coerce_req_scenario(cls, v: Any) -> str:
        if not v or str(v).strip().lower() in ("", "none", "null", "undefined"):
            return "fantasy"
        return str(v).strip()


class ResumeSessionRequest(BaseModel):
    user_id: int
    session_id: int
    character_id: Optional[int] = None


class ActionRequest(BaseModel):
    session_id: int
    user_id: int
    choice_index: Optional[int] = None
    custom_action_text: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    direct_choice: Optional[Dict[str, Any]] = None
    combat_target: Optional[str] = None
    intent: Optional[str] = None
    target_npc: Optional[str] = None
    skip_minutes: Optional[int] = None
    sleep_mode: Optional[str] = None
    is_stealth: Optional[bool] = False
    stance: Optional[str] = None
    item_id: Optional[int] = None
    target_type: Optional[str] = None
    target_name: Optional[str] = None
    target_user_id: Optional[int] = None
    use_mode: Optional[str] = None
    async_ws: Optional[bool] = False


class ToggleStealthRequest(BaseModel):
    session_id: int
    user_id: int
    active: Optional[bool] = None


class ToggleNonLethalRequest(BaseModel):
    session_id: int
    user_id: int
    active: Optional[bool] = None


class EndAdventureRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None


class RetryAdventureRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None
    async_ws: Optional[bool] = False


class CancelTurnRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None


class RerollImageRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None


class MerchantBuyRequest(BaseModel):
    session_id: int
    user_id: int
    item_name: str
    is_phone_shop: Optional[bool] = False
    merchant_type: Optional[str] = None


class MerchantSellRequest(BaseModel):
    session_id: int
    user_id: int
    item_id: int
    is_phone_shop: Optional[bool] = False
    merchant_type: Optional[str] = None


class MerchantHaggleRequest(BaseModel):
    session_id: int
    user_id: int
    is_phone_shop: Optional[bool] = False
    merchant_type: Optional[str] = None


class MerchantRumorRequest(BaseModel):
    session_id: int
    user_id: int
    rumor_index: int
    merchant_type: Optional[str] = None


class PhoneMessageRequest(BaseModel):
    user_id: int
    message: Optional[str] = ""
    intent: Optional[str] = None


class CompanionPartyRequest(BaseModel):
    session_id: int
    user_id: int
    npc_name: str
    action: str = "recruit"


class SaveSlotRequest(BaseModel):
    user_id: int
    slot_name: str
    overwrite: bool = True


class LoadSlotRequest(BaseModel):
    user_id: int
    slot_name: str


class SettingsUpdateRequest(BaseModel):
    user_id: int
    language: Optional[str] = None
    ui_language: Optional[str] = None
    narration_language: Optional[str] = None
    verbosity: Optional[str] = None
    narrative_style: Optional[str] = None
    narrative_pacing: Optional[str] = None
    dialogue_mode: Optional[str] = None
    image_gen_enabled: Optional[int] = None
    choices_style: Optional[str] = None
    result_display: Optional[str] = None
    stream_narrative: Optional[int] = None
    show_percentages: Optional[int] = None
    show_enemy_hp: Optional[int] = None
    show_enemy_intent: Optional[int] = None
    combat_ui_style: Optional[str] = None
    image_model: Optional[str] = None


class DebugUpdateRequest(BaseModel):
    debug_stat_mode: Optional[str] = None
    debug_check_mode: Optional[str] = None
    debug_reveal_all_info: Optional[int] = None
    action: Optional[str] = None
    session_id: Optional[int] = None


class FactionHQActionRequest(BaseModel):
    user_id: int
    faction_id: str
    action: str  # "join" | "leave" | "rest" | "quartermaster" | "promote" | "calibrate"
    attribute: Optional[str] = None
    combat_archetype: Optional[str] = None
    ability_medium: Optional[str] = None
    origin_mode: Optional[str] = None
    student_grade: Optional[str] = None


class PhoneFeedActionRequest(BaseModel):
    user_id: int
    force_refresh: Optional[bool] = True


class PeerPulseDiscoverRequest(BaseModel):
    user_id: int
    query_name: Optional[str] = None


class PeerPulseFriendRequest(BaseModel):
    user_id: int
    profile: Dict[str, Any]


class BountyGenerateRequest(BaseModel):
    user_id: Optional[int] = None
    force_refresh: bool = False
    faction_id: Optional[str] = None


class BountyActionRequest(BaseModel):
    user_id: Optional[int] = None
    quest_id: str
    action: str = "accept"  # "accept" | "abandon"
    haggle_advance: bool = False


class ClueDeductionRequest(BaseModel):
    user_id: Optional[int] = None
    clue_a_id: int
    clue_b_id: Optional[int] = None


class SuspectAccusationRequest(BaseModel):
    user_id: Optional[int] = None
    quest_id: str
    suspect_name: str
    mode: str = "private"  # "private" | "formal"


class QuestTurnInRequest(BaseModel):
    user_id: int
    quest_id: str
    disposition: str = "deliver"  # "deliver" | "side_switch" | "blackmail_client" | "keep" | "destroy" | "fence"


class EpilogueChoiceRequest(BaseModel):
    user_id: Optional[int] = None
    choice_id: str = "endless"  # "archive" | "endless"


class PhoneMediaGenerateRequest(BaseModel):
    user_id: int
    force_regenerate: bool = False



