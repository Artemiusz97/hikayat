from __future__ import annotations
"""
Hikayat - Clues & Caseboard Mechanics Module
Provides evidence categorization, context formatting for LLM turns,
and deductive synthesis logic for combining clues into narrative breakthroughs.
"""
import logging
import re
import db

log = logging.getLogger("hikayat.clues")

CATEGORY_ICONS = {
    "physical": "🔍",
    "testimonial": "🗣️",
    "digital": "💾",
    "document": "📄",
    "deduction": "⚡"
}

TESTIMONIAL_KEYWORDS = {
    "witness", "said", "whisper", "whispered", "admit", "admitted",
    "testified", "overheard", "rumor", "heard", "claimed", "told",
    "confessed", "stated", "interview", "testimony", "interrogation"
}

DIGITAL_KEYWORDS = {
    "phone", "message", "email", "sms", "text", "app", "post",
    "terminal", "net", "network", "hack", "data", "recording",
    "video", "audio", "photo", "peerpulse", "netwire", "server", "code"
}

DOCUMENT_KEYWORDS = {
    "note", "letter", "paper", "diary", "journal", "report",
    "ledger", "blueprint", "document", "file", "record", "archive",
    "receipt", "form", "memo", "schedule", "roster"
}


def categorize_clue(lead_text: str) -> str:
    """Infers the evidence category from lead text keywords."""
    if not lead_text:
        return "physical"
    text_low = lead_text.lower()
    words = set(re.findall(r'\b[a-z]{3,}\b', text_low))

    if words & DIGITAL_KEYWORDS:
        return "digital"
    if words & TESTIMONIAL_KEYWORDS:
        return "testimonial"
    if words & DOCUMENT_KEYWORDS:
        return "document"
    return "physical"


def format_caseboard_prompt_context(session_id: int, max_clues: int = 6) -> str:
    """Formats active leads and verified deductions into an LLM prompt context block."""
    clues = db.get_session_clues(session_id)
    if not clues:
        return ""

    verified = [c for c in clues if c.get("is_verified")]
    open_leads = [c for c in clues if not c.get("is_verified")]

    lines = ["INVESTIGATION EVIDENCE CASEBOARD:"]
    if verified:
        lines.append("• [VERIFIED DEDUCTIONS & FACTS]:")
        for c in verified[:3]:
            icon = CATEGORY_ICONS.get(c.get("category", "physical"), "🔍")
            npc_tag = f" (Linked: {c['linked_npc']})" if c.get("linked_npc") else ""
            lines.append(f"  {icon} {c['title']}: {c['lead_text']}{npc_tag}")

    if open_leads:
        lines.append("• [OPEN LEADS & EVIDENCE UNDER INVESTIGATION]:")
        for c in open_leads[:max_clues]:
            icon = CATEGORY_ICONS.get(c.get("category", "physical"), "🔍")
            loc_tag = f" @ {c['source_location']}" if c.get("source_location") else ""
            npc_tag = f" (Suspect: {c['linked_npc']})" if c.get("linked_npc") else ""
            lines.append(f"  {icon} {c['title']}: {c['lead_text']}{loc_tag}{npc_tag}")

    return "\n".join(lines)


def evaluate_clue_deduction(clue_a: dict, clue_b: dict, scen_key: str = "fantasy") -> tuple[bool, str, str]:
    """
    Evaluates whether two evidence records can be logically connected into a Breakthrough.
    Returns: (is_valid, breakthrough_title, breakthrough_text)
    """
    if not clue_a or not clue_b or clue_a.get("id") == clue_b.get("id"):
        return False, "", "A clue cannot be connected to itself."

    text_a = f"{clue_a.get('title', '')} {clue_a.get('lead_text', '')}".lower()
    text_b = f"{clue_b.get('title', '')} {clue_b.get('lead_text', '')}".lower()

    tokens_a = set(re.findall(r'\b[a-z]{4,}\b', text_a)) - {
        "this", "that", "with", "from", "have", "been", "were", "what",
        "some", "found", "discovered", "lead", "note", "clue", "area"
    }
    tokens_b = set(re.findall(r'\b[a-z]{4,}\b', text_b)) - {
        "this", "that", "with", "from", "have", "been", "were", "what",
        "some", "found", "discovered", "lead", "note", "clue", "area"
    }

    overlap = tokens_a & tokens_b

    # Condition 1: Shared named suspect
    npc_a = str(clue_a.get("linked_npc") or "").strip().lower()
    npc_b = str(clue_b.get("linked_npc") or "").strip().lower()
    has_shared_npc = bool(npc_a and npc_b and (npc_a == npc_b or npc_a in npc_b or npc_b in npc_a))

    # Condition 2: Shared specific venue/location
    loc_a = str(clue_a.get("source_location") or "").strip().lower()
    loc_b = str(clue_b.get("source_location") or "").strip().lower()
    has_shared_loc = bool(loc_a and loc_b and loc_a not in ("unknown", "local area", "peerpulse feed", "social feed") and (loc_a == loc_b or loc_a in loc_b or loc_b in loc_a))

    # Condition 3: Significant keyword overlap (e.g. key, chemical, locker, midnight, stolen)
    has_keyword_synergy = len(overlap) >= 1

    if has_shared_npc or has_shared_loc or has_keyword_synergy:
        anchor = clue_a.get("linked_npc") or clue_b.get("linked_npc") or (list(overlap)[0].title() if overlap else "Evidence")
        title = f"Breakthrough: Connected {anchor}"
        
        detail_reasons = []
        if has_shared_npc:
            detail_reasons.append(f"Both leads directly implicate {anchor}")
        if has_shared_loc:
            detail_reasons.append(f"Physical trails converge at {clue_a.get('source_location') or clue_b.get('source_location')}")
        if overlap:
            matched_words = ", ".join(sorted(list(overlap))[:3])
            detail_reasons.append(f"Corroborating details match: [{matched_words}]")

        reason_str = "; ".join(detail_reasons)
        breakthrough_text = (
            f"By cross-referencing '{clue_a.get('title')}' with '{clue_b.get('title')}', "
            f"a decisive pattern emerges: {reason_str}. "
            f"This confirms the lead and unlocks direct confrontation options!"
        )
        return True, title, breakthrough_text

    return False, "", "These two pieces of evidence do not appear to have an obvious logical connection yet. Explore further or gather corroborating testimony."
