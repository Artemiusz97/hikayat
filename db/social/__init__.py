from __future__ import annotations

from ..core import ReadUnitOfWork, UnitOfWork, get_conn
from .cooldowns import (
    decrement_confession_cooldowns,
    decrement_contact_request_cooldowns,
    decrement_recruitment_cooldowns,
    get_confession_cooldown,
    get_contact_request_cooldown,
    get_phone_social_state,
    get_recruitment_cooldown,
    set_confession_cooldown,
    set_contact_request_cooldown,
    set_recruitment_cooldown,
    update_phone_social_state,
)
from .contacts_enrichment import (
    _LEADING_ROLE_STOPWORDS,
    _POSITION_TITLES_PATTERN,
    _clean_org_name,
    _enrich_contact_basic_info,
    _extract_role_and_affiliation_from_text,
    _is_empty_info_val,
    _merge_basic_info_safely,
)
from .households_factions import (
    _CORE_ROOM_TO_MAJOR_FAC_NODES,
    _MAJOR_CLUB_FACILITY_TO_CORE_ROOM,
    _parse_faction_row,
    _parse_household_row,
    assign_contact_household,
    create_household,
    get_faction,
    get_faction_by_hq,
    get_factions,
    get_household_by_id,
    get_household_by_key,
    get_household_members,
    set_character_faction_membership,
    update_faction_leadership_roster,
    upsert_faction,
)
from .contacts_repo import (
    _apply_contact_household_residence,
    _contact_reentrancy,
    _get_ensuring_scene_set,
    _get_resolving_contacts_set,
    _sync_contact_track_to_social_graph,
    delete_contact,
    ensure_scene_npcs_in_contacts,
    get_contact,
    get_contacts,
    get_session_active_social_ties,
    update_contact_open_thread,
    update_contact_relations,
    update_contact_score,
    update_contact_status_effects,
    update_contact_track,
    update_relationship_score,
    upsert_contact,
)
from .phone_commitments import (
    _commitment_row_to_appointment_dict,
    _resolve_phone_contact_keys,
    expire_overdue_appointments,
    get_active_rendezvous_appointments,
    get_due_reminder_appointments,
    get_gossip_feed,
    get_phone_appointments,
    get_phone_daily_limits,
    get_phone_messages,
    record_phone_daily_interaction,
    save_gossip_feed,
    save_phone_appointment,
    save_phone_message,
    save_rendezvous_appointment,
    update_contact_in_person_timestamp,
    update_phone_appointment_status,
)
from .rosters_snapshots import (
    _ensure_actor_physical_turn_snapshots_table,
    get_anomalous_agent_roster,
    get_school_characters_by_facility,
    get_school_directory_batch,
    get_school_roster,
    mark_school_character_hydrated,
    rollback_actor_physical_state_after_turn,
    save_school_roster,
    snapshot_session_physical_state_for_turn,
)

__all__ = [
    "assign_contact_household",
    "create_household",
    "decrement_confession_cooldowns",
    "decrement_contact_request_cooldowns",
    "decrement_recruitment_cooldowns",
    "delete_contact",
    "ensure_scene_npcs_in_contacts",
    "expire_overdue_appointments",
    "get_active_rendezvous_appointments",
    "get_anomalous_agent_roster",
    "get_confession_cooldown",
    "get_contact",
    "get_contact_request_cooldown",
    "get_contacts",
    "get_due_reminder_appointments",
    "get_faction",
    "get_faction_by_hq",
    "get_factions",
    "get_gossip_feed",
    "get_household_by_id",
    "get_household_by_key",
    "get_household_members",
    "get_phone_appointments",
    "get_phone_daily_limits",
    "get_phone_messages",
    "get_phone_social_state",
    "get_recruitment_cooldown",
    "get_school_characters_by_facility",
    "get_school_directory_batch",
    "get_school_roster",
    "get_session_active_social_ties",
    "mark_school_character_hydrated",
    "record_phone_daily_interaction",
    "rollback_actor_physical_state_after_turn",
    "save_gossip_feed",
    "save_phone_appointment",
    "save_phone_message",
    "save_rendezvous_appointment",
    "save_school_roster",
    "set_character_faction_membership",
    "set_confession_cooldown",
    "set_contact_request_cooldown",
    "set_recruitment_cooldown",
    "snapshot_session_physical_state_for_turn",
    "update_contact_in_person_timestamp",
    "update_contact_open_thread",
    "update_contact_relations",
    "update_contact_score",
    "update_contact_status_effects",
    "update_contact_track",
    "update_faction_leadership_roster",
    "update_phone_appointment_status",
    "update_phone_social_state",
    "update_relationship_score",
    "upsert_contact",
    "upsert_faction",
]

import sys as _sys
import types as _types
from typing import Any as _Any

from . import (
    contacts_enrichment as _mod_contacts_enrichment,
    contacts_repo as _mod_contacts_repo,
    cooldowns as _mod_cooldowns,
    households_factions as _mod_households_factions,
    phone_commitments as _mod_phone_commitments,
    rosters_snapshots as _mod_rosters_snapshots,
)

_SUBMODULES = (
    _mod_cooldowns,
    _mod_contacts_enrichment,
    _mod_households_factions,
    _mod_contacts_repo,
    _mod_phone_commitments,
    _mod_rosters_snapshots,
)
_SUBMODULE_NAMES = frozenset(
    {
        "cooldowns",
        "contacts_enrichment",
        "households_factions",
        "contacts_repo",
        "phone_commitments",
        "rosters_snapshots",
    }
)


class _SocialPackageModule(_types.ModuleType):
    """Propagates attribute rebindings on `db.social` to child submodules for monolithic-module parity."""

    def __setattr__(self, name: str, value: _Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__") and name not in _SUBMODULE_NAMES:
            for _sub in _SUBMODULES:
                if name in _sub.__dict__:
                    setattr(_sub, name, value)

    def __delattr__(self, name: str) -> None:
        super().__delattr__(name)
        if not name.startswith("__") and name not in _SUBMODULE_NAMES:
            for _sub in _SUBMODULES:
                if name in _sub.__dict__:
                    delattr(_sub, name)


_sys.modules[__name__].__class__ = _SocialPackageModule
