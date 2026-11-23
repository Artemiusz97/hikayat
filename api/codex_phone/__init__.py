from __future__ import annotations

from fastapi import APIRouter

import db
from db import adb
from db.core.module_proxy import install_submodule_proxy as _install_submodule_proxy
import game_engine
import mechanics.narrative.bounty
import mechanics.social.genealogy
import mechanics.social.persona
import mechanics.social.relationships
from mechanics.system.concurrency import (
    distributed_adventure_lock,
    distributed_session_lock,
    distributed_user_lock,
)
from mechanics.system.phone import (
    detect_custom_message_intent,
    discover_suggested_peer,
    generate_contact_dm_reply,
    generate_gossip_feed_posts,
    generate_phone_media_image,
    generate_player_chat_message,
    get_phone_branding,
    get_social_state_summary,
    get_suggested_peers,
    is_media_item_in_flight,
    is_session_image_gen_enabled,
    lookup_social_profile,
    resolve_social_friend_request,
    scour_feed_for_rumor,
    spawn_phone_media_image_task,
)
from services.examine_service import invalidate_examine_cache
from ..deps import (
    BountyActionRequest,
    BountyGenerateRequest,
    ClueDeductionRequest,
    CompanionPartyRequest,
    EpilogueChoiceRequest,
    FactionHQActionRequest,
    PeerPulseDiscoverRequest,
    PeerPulseFriendRequest,
    PhoneFeedActionRequest,
    PhoneMediaGenerateRequest,
    PhoneMessageRequest,
    QuestTurnInRequest,
    SuspectAccusationRequest,
    manager,
    serializable_action,
)

_serializable_action = serializable_action
from ..encyclopedia import get_codex_encyclopedia
from ..security import (
    extract_actor_token,
    extract_verified_token_uid,
    is_strict_auth_context,
    verify_session_participant,
    verify_user_access,
)
from . import (
    common as _mod_common,
    contacts as _mod_contacts,
    factions as _mod_factions,
    lorebook as _mod_lorebook,
    party as _mod_party,
    phone as _mod_phone,
    quests as _mod_quests,
)
from .common import (
    CancelCommitmentRequest,
    _enrich_commitments_for_ui,
    _fmt_hhmm,
    _get_contacts_ro,
    _infer_school_grade_badge,
    _verify_missing_session_codex_auth,
)
from .contacts import (
    _build_acquaintance_input_dict,
    _build_contacts_and_acquaintances_payload,
    _collect_contact_identity_keys,
    _enrich_contact_record,
    _extract_player_last_name,
    _index_npc_records,
    _lookup_indexed_npc,
    _preload_fog_of_war_context,
    _resolve_faction_affiliation,
    get_contacts,
)
from .factions import (
    _enrich_factions_list,
    _execute_faction_hq_action,
    faction_hq_action,
    get_factions,
)
from .lorebook import (
    _format_world_lore_entity_for_ui,
    get_lorebook,
)
from .party import (
    _execute_manage_party_companion,
    manage_party_companion,
)
from .phone import (
    cancel_session_commitment,
    discover_peerpulse_profile,
    generate_phone_media,
    get_npc_messages,
    get_peerpulse_suggestions,
    get_phone_state,
    refresh_phone_feed,
    scour_phone_feed,
    send_npc_message,
    send_peerpulse_friend_request,
)
from .quests import (
    _build_quests_payload,
    accuse_caseboard_suspect,
    bounty_contract_action,
    deduce_caseboard_clues,
    generate_session_bounties,
    get_quests,
    resolve_campaign_epilogue_choice,
    resolve_contract_turn_in,
)

router = APIRouter()
router.include_router(_mod_party.router)
router.include_router(_mod_lorebook.router)
router.include_router(_mod_contacts.router)
router.include_router(_mod_factions.router)
router.include_router(_mod_quests.router)
router.include_router(_mod_phone.router)

_SUBMODULES = (
    _mod_common,
    _mod_party,
    _mod_lorebook,
    _mod_contacts,
    _mod_factions,
    _mod_quests,
    _mod_phone,
)
_SUBMODULE_NAMES = frozenset(
    {"common", "party", "lorebook", "contacts", "factions", "quests", "phone"}
)

_install_submodule_proxy(__name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_CodexPhonePackageModule")

__all__ = [
    "BountyActionRequest",
    "BountyGenerateRequest",
    "CancelCommitmentRequest",
    "ClueDeductionRequest",
    "CompanionPartyRequest",
    "EpilogueChoiceRequest",
    "FactionHQActionRequest",
    "PeerPulseDiscoverRequest",
    "PeerPulseFriendRequest",
    "PhoneFeedActionRequest",
    "PhoneMediaGenerateRequest",
    "PhoneMessageRequest",
    "QuestTurnInRequest",
    "SuspectAccusationRequest",
    "_build_acquaintance_input_dict",
    "_build_contacts_and_acquaintances_payload",
    "_build_quests_payload",
    "_collect_contact_identity_keys",
    "_enrich_commitments_for_ui",
    "_enrich_contact_record",
    "_enrich_factions_list",
    "_execute_faction_hq_action",
    "_execute_manage_party_companion",
    "_extract_player_last_name",
    "_fmt_hhmm",
    "_format_world_lore_entity_for_ui",
    "_get_contacts_ro",
    "_index_npc_records",
    "_infer_school_grade_badge",
    "_lookup_indexed_npc",
    "_preload_fog_of_war_context",
    "_resolve_faction_affiliation",
    "_serializable_action",
    "_verify_missing_session_codex_auth",
    "accuse_caseboard_suspect",
    "adb",
    "bounty_contract_action",
    "cancel_session_commitment",
    "db",
    "deduce_caseboard_clues",
    "detect_custom_message_intent",
    "discover_peerpulse_profile",
    "discover_suggested_peer",
    "distributed_adventure_lock",
    "distributed_session_lock",
    "distributed_user_lock",
    "extract_actor_token",
    "extract_verified_token_uid",
    "faction_hq_action",
    "game_engine",
    "generate_contact_dm_reply",
    "generate_gossip_feed_posts",
    "generate_phone_media",
    "generate_phone_media_image",
    "generate_player_chat_message",
    "generate_session_bounties",
    "get_codex_encyclopedia",
    "get_contacts",
    "get_factions",
    "get_lorebook",
    "get_npc_messages",
    "get_peerpulse_suggestions",
    "get_phone_branding",
    "get_phone_state",
    "get_quests",
    "get_social_state_summary",
    "get_suggested_peers",
    "invalidate_examine_cache",
    "is_media_item_in_flight",
    "is_session_image_gen_enabled",
    "is_strict_auth_context",
    "lookup_social_profile",
    "manage_party_companion",
    "manager",
    "mechanics",
    "refresh_phone_feed",
    "resolve_campaign_epilogue_choice",
    "resolve_contract_turn_in",
    "resolve_social_friend_request",
    "router",
    "scour_feed_for_rumor",
    "scour_phone_feed",
    "send_npc_message",
    "send_peerpulse_friend_request",
    "spawn_phone_media_image_task",
    "verify_session_participant",
    "verify_user_access",
]
