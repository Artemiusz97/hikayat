from __future__ import annotations

from .roster_tags import (
    AgeGroup,
    AGE_GROUP_TEEN,
    AGE_GROUP_ADULT,
    derive_age_group,
    normalize_standing,
    normalize_social_role_type,
    is_contact_eligible_demographic,
    is_merchant_character,
    is_student_character,
    resolve_character_badges,
    get_dialogue_register,
    format_dialogue_register_directive,
)
from .genealogy import get_or_generate_family_tree
from .factions import is_school_club_faction, get_faction_category_tag

__all__ = [
    "AgeGroup",
    "AGE_GROUP_TEEN",
    "AGE_GROUP_ADULT",
    "derive_age_group",
    "normalize_standing",
    "normalize_social_role_type",
    "is_contact_eligible_demographic",
    "is_merchant_character",
    "is_student_character",
    "resolve_character_badges",
    "get_dialogue_register",
    "format_dialogue_register_directive",
    "get_or_generate_family_tree",
    "is_school_club_faction",
    "get_faction_category_tag",
]
