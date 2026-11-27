from __future__ import annotations
"""Package root facade for REALM boundaries, hierarchy, portals, vessels, lifecycle, and summary."""

from .choices import get_portal_choices_at_node
from .constants import (
    DEFAULT_REALM_RULES,
    DYNAMIC_REALM_TEMPLATES,
    PORTAL_EDGE_TYPES,
    _default_primary_realm_meta,
    _slugify_id,
)
from .hierarchy import (
    _format_tiered_location_in_memory,
    check_realm_comms_available,
    find_nearest_access_point_for_realm,
    format_tiered_location_in_memory,
    get_node_ancestors_in_memory,
    get_node_hierarchy_roles_in_memory,
    get_node_realm,
    get_node_realm_id,
    get_node_realm_id_in_memory,
    get_node_realm_in_memory,
    get_portal_edges_in_memory,
    get_primary_realm_in_memory,
    get_realm_rules,
    get_realm_rules_for_node,
    get_realm_time_scale,
    get_session_realms,
    is_at_access_point_in_memory,
    is_node_or_realm_hidden_in_memory,
    parse_node_state_json,
)
from .lifecycle import (
    collapse_dynamic_realm,
    discover_realm,
    ensure_default_realm_wrapper,
    pacify_dynamic_realm,
    rollback_realm_state_after_turn,
    spawn_dynamic_realm,
)
from .summary import build_session_realm_summary
from .vessels import (
    execute_recall_starship,
    execute_starship_jump,
)

__all__ = [
    "PORTAL_EDGE_TYPES",
    "DEFAULT_REALM_RULES",
    "DYNAMIC_REALM_TEMPLATES",
    "_slugify_id",
    "_default_primary_realm_meta",
    "format_tiered_location_in_memory",
    "_format_tiered_location_in_memory",
    "parse_node_state_json",
    "get_realm_rules",
    "get_node_ancestors_in_memory",
    "get_node_hierarchy_roles_in_memory",
    "get_node_realm_in_memory",
    "get_node_realm_id_in_memory",
    "is_node_or_realm_hidden_in_memory",
    "is_at_access_point_in_memory",
    "get_primary_realm_in_memory",
    "get_portal_edges_in_memory",
    "get_node_realm",
    "get_node_realm_id",
    "get_session_realms",
    "get_realm_rules_for_node",
    "get_realm_time_scale",
    "check_realm_comms_available",
    "find_nearest_access_point_for_realm",
    "get_portal_choices_at_node",
    "execute_starship_jump",
    "execute_recall_starship",
    "ensure_default_realm_wrapper",
    "discover_realm",
    "spawn_dynamic_realm",
    "pacify_dynamic_realm",
    "collapse_dynamic_realm",
    "rollback_realm_state_after_turn",
    "build_session_realm_summary",
]
