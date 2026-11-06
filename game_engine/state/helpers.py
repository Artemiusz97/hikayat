from __future__ import annotations

from typing import Any

__all__ = [
    "extract_scene_fields",
    "get_combined_narrative",
    "is_check_success",
]

# Pre-compiled frozen sets for O(1) membership checking
_SUCCESS_TIERS: frozenset[str] = frozenset({
    "success",
    "critical_success",
    "crit_success",
    "partial_success",
})

_FAILURE_TIERS: frozenset[str] = frozenset({
    "fail",
    "failure",
    "crit_fail",
    "critical_fail",
    "critical_failure",
})

_CHOICE_KEYS: tuple[str, ...] = (
    "next_choices",
    "choices",
    "actions",
    "options",
    "suggested_actions",
    "next_actions",
)

_NARRATIVE_KEYS: tuple[str, ...] = (
    "next_narrative",
    "narrative",
    "outcome_narrative",
    "story",
    "scene_text",
    "description",
)

_TITLE_KEYS: tuple[str, ...] = (
    "scene_title",
    "title",
    "name",
    "scene_name",
)


def _coerce_bool(val: Any) -> bool | None:
    """Safely coerce truthy/falsy values, guarding against LLM string boolean traps."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        clean = val.strip().lower()
        if clean in ("true", "1", "yes", "t", "y"):
            return True
        if clean in ("false", "0", "no", "f", "n"):
            return False
    return bool(val)


def is_check_success(check_obj: Any, default_if_none: bool = True) -> bool:
    """Canonical evaluator for stat/skill check success across all engine structures.

    Safely handles CheckResult objects, dicts, booleans, and uppercase/lowercase tier strings.
    """
    if check_obj is None:
        return bool(default_if_none)
    if isinstance(check_obj, bool):
        return check_obj
    if isinstance(check_obj, str):
        clean = check_obj.strip().lower()
        if clean in _SUCCESS_TIERS:
            return True
        if clean in _FAILURE_TIERS:
            return False
        return bool(default_if_none)

    # Fast path 1: dict (most common serialized form) - zero getattr/AttributeError overhead
    if isinstance(check_obj, dict):
        for key in ("succeeded", "is_success", "success"):
            if key in check_obj:
                coerced = _coerce_bool(check_obj[key])
                if coerced is not None:
                    return coerced
        for key in ("tier", "result_tier"):
            val = check_obj.get(key)
            if val is not None:
                s_val = str(val).strip().lower()
                if s_val in _SUCCESS_TIERS:
                    return True
                if s_val in _FAILURE_TIERS:
                    return False
        return bool(default_if_none)

    # Fast path 2: object (CheckResult dataclass, Pydantic model)
    for attr in ("succeeded", "is_success", "success"):
        try:
            val = getattr(check_obj, attr, None)
            coerced = _coerce_bool(val)
            if coerced is not None:
                return coerced
        except Exception:
            pass

    for attr in ("tier", "result_tier"):
        try:
            val = getattr(check_obj, attr, None)
            if val is not None:
                s_val = str(val).strip().lower()
                if s_val in _SUCCESS_TIERS:
                    return True
                if s_val in _FAILURE_TIERS:
                    return False
        except Exception:
            pass

    return bool(default_if_none)


def get_combined_narrative(outcome: Any) -> str:
    """Canonical helper to extract and combine all narrative fields from an outcome dict or model."""
    if outcome is None:
        return ""

    data: Any = outcome
    if hasattr(data, "model_dump") and callable(data.model_dump):
        try:
            data = data.model_dump(exclude_unset=False)
        except Exception:
            data = outcome

    is_dict = isinstance(data, dict)
    parts: list[str] = []

    for key in ("outcome_narrative", "next_narrative", "narrative"):
        if is_dict:
            val = data.get(key)
        else:
            try:
                val = getattr(data, key, None)
            except Exception:
                val = None

        if val and not isinstance(val, (dict, list, tuple, set)):
            s = str(val).strip()
            if s:
                parts.append(s)

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " ".join(parts)


def extract_scene_fields(
    data: Any,
    session: dict[str, Any] | None = None,
    default_narrative: str = "",
) -> tuple[list[dict[str, Any]], str, str, Any, list[Any]]:
    """Canonical helper to extract and normalize choices, narrative, scene_title, dialogue_partner, and npcs from LLM scene/outcome dicts."""
    if data is None:
        raw_dict: dict[str, Any] = {}
    elif hasattr(data, "model_dump") and callable(data.model_dump):
        try:
            raw_dict = data.model_dump(exclude_unset=False)
        except Exception:
            raw_dict = {}
    elif isinstance(data, dict):
        raw_dict = data
    else:
        raw_dict = {}

    sess_dict = session if isinstance(session, dict) else {}

    raw_choices = None
    for k in _CHOICE_KEYS:
        val = raw_dict.get(k)
        if val:
            raw_choices = val
            break
    if not raw_choices:
        raw_choices = []
    elif not isinstance(raw_choices, (list, tuple)):
        raw_choices = [raw_choices]

    normalized_choices: list[dict[str, Any]] = []
    for c in raw_choices:
        if not c:
            continue
        if isinstance(c, dict):
            normalized_choices.append(c)
        elif hasattr(c, "model_dump") and callable(c.model_dump):
            try:
                normalized_choices.append(c.model_dump(exclude_unset=True))
            except Exception:
                normalized_choices.append({"label": str(c)})
        else:
            normalized_choices.append({"label": str(c)})

    raw_narrative = None
    for k in _NARRATIVE_KEYS:
        val = raw_dict.get(k)
        if val:
            raw_narrative = val
            break
    if not raw_narrative:
        if sess_dict.get("narrative") and default_narrative:
            raw_narrative = sess_dict.get("narrative")
        elif default_narrative:
            raw_narrative = default_narrative
        else:
            raw_narrative = ""

    if isinstance(raw_narrative, (list, tuple)):
        next_narrative = " ".join(str(p).strip() for p in raw_narrative if p).strip()
    else:
        next_narrative = str(raw_narrative).strip()

    scene_title = ""
    for k in _TITLE_KEYS:
        val = raw_dict.get(k)
        if val:
            scene_title = str(val).strip()
            break
    if not scene_title and sess_dict.get("scene_title"):
        scene_title = str(sess_dict["scene_title"]).strip()
    if not scene_title:
        scene_title = "Hikayat"

    partner_arg = (
        raw_dict.get("dialogue_partners")
        if raw_dict.get("dialogue_partners") is not None
        else raw_dict.get("dialogue_partner")
    )

    if raw_dict.get("npcs_present") is not None:
        raw_npcs = raw_dict.get("npcs_present")
    elif raw_dict.get("current_npcs") is not None:
        raw_npcs = raw_dict.get("current_npcs")
    else:
        raw_npcs = sess_dict.get("current_npcs", [])

    if isinstance(raw_npcs, (list, tuple)):
        npcs_arg = [n for n in raw_npcs if n]
    elif raw_npcs:
        npcs_arg = [raw_npcs]
    else:
        npcs_arg = []

    has_exited = bool(
        raw_dict.get("has_exited_convo")
        or sess_dict.get("has_exited_convo")
    )

    if partner_arg == "__NOOP__" or partner_arg == ["__NOOP__"]:
        partner_arg = None

    if has_exited:
        # Player explicitly exited the conversation: strictly clear dialogue partner
        partner_arg = None

    return normalized_choices, next_narrative, scene_title, partner_arg, npcs_arg
