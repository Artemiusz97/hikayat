"""Quest dossier, campaign spine, folklore encyclopedia, and anomaly record persistence package."""
from __future__ import annotations

from ..core import get_conn
from ..core.module_proxy import install_submodule_proxy as _install_submodule_proxy
from . import (
    anomaly_records as _mod_anomaly_records,
    discoveries as _mod_discoveries,
    folklore as _mod_folklore,
    profiles as _mod_profiles,
)
from .anomaly_records import (
    SESSION_ANOMALY_KEY_TO_RECORD_TYPE,
    _RECORD_TYPE_TO_SESSION_ANOMALY_KEY,
    _extract_anomaly_record_columns,
    get_session_anomaly_records,
    hydrate_session_anomaly_records,
    record_session_anomaly_field_log,
    retire_or_cooldown_folklore_in_session,
    rollback_session_anomaly_logs_after_turn,
    sync_session_anomaly_records_from_extra,
)
from .discoveries import (
    _TRACKED_DOSSIER_STATE_FIELDS,
    _merge_dedup_state_event,
    _rebase_climax_snapshot,
    _rebase_clue_graph_snapshot,
    _rebase_leads_graph_snapshot,
    append_dossier_state_event,
    append_spine_state_event,
    rollback_quest_dossiers_after_turn,
    upsert_quest_dossier,
)
from .folklore import (
    _FOLKLORE_STAGE_RANK,
    get_user_folklore_codex,
    get_users_folklore_codex_batch,
    record_folklore_codex_progress,
    user_has_folklore_recognition,
)
from .profiles import (
    _deserialize_json_field,
    _effective_session_turn,
    _enrich_dossier_dict,
    _enrich_spine_dict,
    _json_str,
    get_campaign_spine,
    get_effective_session_turn,
    get_prewarmed_quest_dossier,
    get_quest_dossier,
    get_session_participant_user_ids,
    get_session_quest_dossiers,
    normalize_clue_graph_nodes,
    promote_prewarmed_dossier,
    upsert_campaign_spine,
)

_SUBMODULES = (_mod_profiles, _mod_discoveries, _mod_folklore, _mod_anomaly_records)
_SUBMODULE_NAMES = frozenset({"profiles", "discoveries", "folklore", "anomaly_records"})

_install_submodule_proxy(__name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_DossiersPackageModule")

__all__ = [
    "SESSION_ANOMALY_KEY_TO_RECORD_TYPE",
    "_FOLKLORE_STAGE_RANK",
    "_RECORD_TYPE_TO_SESSION_ANOMALY_KEY",
    "_TRACKED_DOSSIER_STATE_FIELDS",
    "_deserialize_json_field",
    "_effective_session_turn",
    "_enrich_dossier_dict",
    "_enrich_spine_dict",
    "_extract_anomaly_record_columns",
    "_json_str",
    "_merge_dedup_state_event",
    "_rebase_climax_snapshot",
    "_rebase_clue_graph_snapshot",
    "_rebase_leads_graph_snapshot",
    "append_dossier_state_event",
    "append_spine_state_event",
    "get_campaign_spine",
    "get_conn",
    "get_effective_session_turn",
    "get_prewarmed_quest_dossier",
    "get_quest_dossier",
    "get_session_anomaly_records",
    "get_session_participant_user_ids",
    "get_session_quest_dossiers",
    "get_user_folklore_codex",
    "get_users_folklore_codex_batch",
    "hydrate_session_anomaly_records",
    "normalize_clue_graph_nodes",
    "promote_prewarmed_dossier",
    "record_folklore_codex_progress",
    "record_session_anomaly_field_log",
    "retire_or_cooldown_folklore_in_session",
    "rollback_quest_dossiers_after_turn",
    "rollback_session_anomaly_logs_after_turn",
    "sync_session_anomaly_records_from_extra",
    "upsert_campaign_spine",
    "upsert_quest_dossier",
    "user_has_folklore_recognition",
]
