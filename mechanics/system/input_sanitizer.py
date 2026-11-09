from __future__ import annotations

"""
Deterministic input boundary sanitizers and XML prompt fences for untrusted player strings.
Prevents delimiter breakout, fake engine directives ([PRE-TURN ...], [SYSTEM DIRECTIVE]),
and item/gear JSON tag spoofing ([ITEM_JSON], [GEAR_JSON], [SPELLBOOK_JSON]) while preserving
legitimate roleplay prose and multi-paragraph custom scenario/class descriptions.
"""

import re
from typing import Optional

_ENVELOPE_BLOCK_RE = re.compile(
    r"\[(?:ITEM_JSON|GEAR_JSON|SPELLBOOK_JSON)\b[^\]]*\].*?\[/\s*(?:ITEM_JSON|GEAR_JSON|SPELLBOOK_JSON)\s*\]",
    re.IGNORECASE | re.DOTALL,
)

_TRAILING_ENVELOPE_RE = re.compile(
    r"\[\s*(?:ITEM_JSON|GEAR_JSON|SPELLBOOK_JSON)\s*\]\s*(?:\{[^\n]*\}|\[[^\n]*\])?",
    re.IGNORECASE,
)

_RESERVED_BRACKET_TAG_RE = re.compile(
    r"\[\s*/?\s*(?:"
    r"ITEM_JSON|GEAR_JSON|SPELLBOOK_JSON|"
    r"[^\]]*\bDIRECTIVE\b[^\]]*|"
    r"[^\]]*\bDIRECTOR\b[^\]]*|"
    r"[^\]]*\bOVERRIDE\b[^\]]*|"
    r"PRE-TURN[^\]]*|"
    r"SYSTEM\b[^\]]*|"
    r"STAGE\s+DIRECTION[^\]]*|"
    r"MANDATORY\s+HAZARD[^\]]*|"
    r"NON-COMBAT\s*/\s*SOCIAL\s+RULE[^\]]*"
    r")\]",
    re.IGNORECASE,
)

_ROLE_HEADER_SPOOF_RE = re.compile(
    r"(?:^|\n|[ \t])#{2,6}[ \t]*(?:SYSTEM|ASSISTANT|DEVELOPER|USER|DIRECTOR|INSTRUCTIONS?)\b[^\n]*",
    re.IGNORECASE,
)

_RESERVED_XML_FENCE_RE = re.compile(
    r"</?\s*(?:player_action|player_message|custom_lore|system|instructions?)\b[^>]*>",
    re.IGNORECASE,
)

_OUTCOME_SPOOF_RE = re.compile(r"->\s*outcome\b[^:]*:", re.IGNORECASE)
_CTRL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_reserved_tokens(text: str) -> str:
    cleaned = _CTRL_CHARS_RE.sub("", str(text or ""))
    cleaned = _ENVELOPE_BLOCK_RE.sub(" ", cleaned)
    cleaned = _TRAILING_ENVELOPE_RE.sub(" ", cleaned)
    cleaned = _RESERVED_BRACKET_TAG_RE.sub(" ", cleaned)
    cleaned = _RESERVED_XML_FENCE_RE.sub(" ", cleaned)
    cleaned = _ROLE_HEADER_SPOOF_RE.sub(" ", cleaned)
    return cleaned


def sanitize_character_name(raw: Optional[str], max_len: int = 60, fallback: str = "") -> str:
    """Single-line character/actor name sanitizer (strips brackets, angle tags, newlines, and excess length)."""
    cleaned = _strip_reserved_tokens(raw or "")
    cleaned = re.sub(r"[\[\]<>\"'`\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned if cleaned else fallback


def sanitize_prompt_lore(raw: Optional[str], max_len: int = 2000) -> str:
    """Multi-paragraph custom class/race/scenario lore sanitizer preserving natural paragraph breaks."""
    cleaned = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _strip_reserved_tokens(cleaned)
    cleaned = _OUTCOME_SPOOF_RE.sub("->", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def wrap_custom_lore(raw: Optional[str], max_len: int = 2000) -> str:
    """Sanitizes custom lore and wraps it inside <custom_lore>...</custom_lore> if non-empty."""
    cleaned = sanitize_prompt_lore(raw, max_len=max_len)
    if not cleaned:
        return ""
    return f"<custom_lore>{cleaned}</custom_lore>"


def fence_player_action(raw: Optional[str], max_len: int = 400) -> str:
    """Single-line XML fence for player action labels entering turn/classification prompts."""
    cleaned = _strip_reserved_tokens(raw or "")
    cleaned = _OUTCOME_SPOOF_RE.sub("->", cleaned)
    cleaned = re.sub(r"[\r\n\t<>]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return f"<player_action>{cleaned}</player_action>"


def fence_player_message(raw: Optional[str], max_len: int = 500) -> str:
    """Single-line XML fence for player phone/SMS text messages entering side-channel prompts."""
    cleaned = _strip_reserved_tokens(raw or "")
    cleaned = re.sub(r"[\r\n\t<>]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return f"<player_message>{cleaned}</player_message>"
