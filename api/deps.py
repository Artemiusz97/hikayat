import logging
from typing import Dict, List, Optional, Any
from fastapi import WebSocket
from pydantic import BaseModel, Field

import db
from db import adb
import skill_check
import character_data as cd

logger = logging.getLogger("hikayat-server")


class ConnectionManager:
    """WebSocket Connection Manager for Multiplayer Lobbies & Live Streaming."""

    def __init__(self):
        self.active_connections: Dict[int, List[Dict[str, Any]]] = {}

    async def connect(self, session_id: int, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append({"ws": websocket, "user_id": user_id})
        logger.info(f"User {user_id} connected to WebSocket session {session_id}")
        await self.broadcast_presence(session_id)

    def disconnect(self, session_id: int, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id] = [
                c for c in self.active_connections[session_id] if c["ws"] != websocket
            ]
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast_presence(self, session_id: int):
        if session_id not in self.active_connections:
            return
        members = await adb(db.get_session_members, session_id)
        connected_uids = [c["user_id"] for c in self.active_connections[session_id]]

        member_profiles = []
        for uid in members:
            c = await adb(db.get_character, uid)
            member_profiles.append({
                "user_id": uid,
                "name": c["name"] if c else f"User {uid}",
                "level": c["level"] if c else 1,
                "online": uid in connected_uids
            })

        payload = {
            "type": "PRESENCE_UPDATE",
            "session_id": session_id,
            "members": member_profiles
        }
        await self.broadcast(session_id, payload)

    async def broadcast(self, session_id: int, message: dict):
        if session_id not in self.active_connections:
            return
        for conn in list(self.active_connections[session_id]):
            try:
                await conn["ws"].send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {conn['user_id']}: {e}")


manager = ConnectionManager()


def _serializable_action(action: dict) -> dict:
    """Returns a copy of the action dict safe for json.dumps (no raw dataclass objects)."""
    safe = {}
    for k, v in action.items():
        if hasattr(v, "__dict__") and not isinstance(v, dict):
            safe[k] = v.__dict__
        else:
            safe[k] = v
    return safe


def enrich_choices_with_odds(choices: list, user_id: int) -> list:
    """Enriches scene choices with calculated success_pct, chance, and Discord-matching action icons."""
    from cogs.adventure.embeds import (
        _get_choice_quest_icon,
        _get_choice_skill_emoji,
        _get_choice_emoji,
    )

    char = db.get_character(user_id) if user_id else None
    user_settings = db.get_settings(char["user_id"]) if char else {}
    check_mode = (user_settings or {}).get("debug_check_mode", "off")

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


def enrich_session_party_members(session_dict: dict) -> list:
    """Fetches real-time vitals and status effects for all human characters in the party."""
    session_id = session_dict.get("id")
    if not session_id:
        return []
    uids = db.get_session_members(session_id)
    if not uids and session_dict.get("host_user_id"):
        uids = [session_dict["host_user_id"]]
    members = []
    for uid in uids:
        c = db.get_character(uid)
        if c:
            members.append({
                "user_id": uid,
                "character_id": c.get("id"),
                "name": c.get("name"),
                "char_class": c.get("char_class"),
                "level": c.get("level", 1),
                "hp": c.get("hp", 0),
                "max_hp": c.get("max_hp", 0),
                "mp": c.get("mp", 0),
                "max_mp": c.get("max_mp", 0),
                "gold": c.get("gold", 0),
                "status_effects": cd.sanitize_status_effects(c.get("status_effects") or []),
                "gender": c.get("gender"),
                "scenario": c.get("scenario"),
            })
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
    starting_weapon: Optional[str] = "Rusty Sword"
    starting_weapon_description: Optional[str] = ""
    starter_loadout: Optional[dict] = None
    str_val: int = Field(1, ge=1, le=10, alias="str")
    per: int = Field(1, ge=1, le=10)
    end: int = Field(1, ge=1, le=10)
    cha: int = Field(1, ge=1, le=10)
    int_val: int = Field(1, ge=1, le=10, alias="int")
    agi: int = Field(1, ge=1, le=10)
    luk: int = Field(1, ge=1, le=10)


class PreviewGearRequest(BaseModel):
    char_class: Optional[str] = "Warrior"
    class_description: Optional[str] = ""
    scenario: Optional[str] = "fantasy"
    tags: Optional[list[str] | str] = None
    gender: Optional[str] = "Male"
    race: Optional[str] = "Human"
    starting_weapon: Optional[str] = ""
    force_dynamic: Optional[bool] = True


class RegenerateGearRequest(BaseModel):
    user_id: int


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
    session_id: Optional[int] = None


class JoinAdventureRequest(BaseModel):
    user_id: int
    join_code: str


class StartAdventureRequest(BaseModel):
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



class ActionRequest(BaseModel):
    session_id: int
    user_id: int
    choice_index: Optional[int] = None
    custom_action_text: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    direct_choice: Optional[Dict[str, Any]] = None
    combat_target: Optional[str] = None


class EndAdventureRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None


class RetryAdventureRequest(BaseModel):
    session_id: int
    user_id: Optional[int] = None


class MerchantBuyRequest(BaseModel):
    session_id: int
    user_id: int
    item_name: str
    is_phone_shop: Optional[bool] = False
    merchant_type: Optional[str] = "general_merchant"


class MerchantSellRequest(BaseModel):
    session_id: int
    user_id: int
    item_id: int


class MerchantHaggleRequest(BaseModel):
    session_id: int
    user_id: int
    merchant_type: Optional[str] = "general_merchant"


class MerchantRumorRequest(BaseModel):
    session_id: int
    user_id: int
    rumor_index: int
    merchant_type: Optional[str] = "general_merchant"


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
    verbosity: Optional[str] = "normal"
    dialogue_mode: Optional[str] = "balanced"
    image_gen_enabled: Optional[int] = 0
    choices_style: Optional[str] = "dropdown"
    result_display: Optional[str] = "detailed"
    stream_narrative: Optional[int] = 1
    show_percentages: Optional[int] = 1
    combat_ui_style: Optional[str] = "battle_deck"
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
    action: str  # "join" | "leave" | "rest" | "quartermaster" | "promote"


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


class BountyActionRequest(BaseModel):
    user_id: Optional[int] = None
    quest_id: str
    action: str = "accept"  # "accept" | "abandon"


class ClueDeductionRequest(BaseModel):
    user_id: Optional[int] = None
    clue_a_id: int
    clue_b_id: int


