"""JSON extraction, reasoning-tag stripping, and Sentinel narration protocol parsers."""
from __future__ import annotations

import json
import re
from typing import Any, Type

import json_repair
from pydantic import BaseModel

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_SENTINEL_HEADER_RE = re.compile(
    r"^\s*(?:#{1,4}\s*|\*\*|\[)?@@\s*(TITLE|OUTCOME(?:_NARRATIVE)?|NEXT(?:_NARRATIVE|_CHOICES)?|CHOICES|META)\b[\]\*:\s]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_THINK_TAG_RE = re.compile(
    r"(?:<(think|thinking|thought)>.*?</\1>|<\|thought\|>.*?(?:<\|/?thought\|>|<\|end_of_thought\|>))",
    re.DOTALL | re.IGNORECASE,
)
_ORPHAN_CLOSE_THINK_RE = re.compile(
    r"^.*?(?:</(?:think|thinking|thought)>|<\|/thought\|>|<\|end_of_thought\|>)\s*",
    re.DOTALL | re.IGNORECASE,
)
_UNCLOSED_OPEN_THINK_TO_FENCE_RE = re.compile(
    r"(?:<(?:think|thinking|thought)>|<\|thought\|>).*?(?=```|(?:^|\n)\s*(?:#{1,4}\s*|\*\*|\[)?@@\s*(?:TITLE|OUTCOME(?:_NARRATIVE)?|NEXT(?:_NARRATIVE)?)\b|\n\s*\{\s*\")",
    re.DOTALL | re.IGNORECASE,
)

_CHOICE_ONLY_KEYS = frozenset(
    {
        "label",
        "text",
        "stat",
        "requirement",
        "ends_dialogue",
        "topic_id",
        "category",
        "combat_target",
        "mp_cost",
        "action_type",
        "target",
        "item_name",
    }
)

_SENTINEL_STAT_SET = frozenset(
    {"STR", "PER", "END", "CHA", "INT", "AGI", "LUK", "ITEM", "NONE", "FREE"}
)
_REFUSAL_PROSE_RE = re.compile(
    r"\b(?:i cannot fulfill|i'm sorry,?\s*(?:but\s*)?i can(?:not|'t)|i am unable to (?:generate|assist|fulfill)|as an ai\b|cannot assist with that|violates my (?:safety|policy|guidelines))\b",
    re.IGNORECASE,
)


def _find_balanced_json_blocks(text: str) -> list[str]:
    """Scan text and extract top-level balanced {...} JSON string blocks,
    properly respecting string literal escaping."""
    blocks = []
    in_string = False
    escape = False
    brace_depth = 0
    start_idx = -1

    for i, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif char == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                    if brace_depth == 0 and start_idx != -1:
                        blocks.append(text[start_idx : i + 1])
                        start_idx = -1
    return blocks


def _strip_reasoning_blocks(raw_text: str, *, preserve_trailing: bool = False) -> str:
    """Remove matched, orphaned, or truncated reasoning/thought tag blocks before JSON or Sentinel parsing."""
    trim = (lambda s: s.lstrip()) if preserve_trailing else (lambda s: s.strip())
    cleaned = trim(_THINK_TAG_RE.sub("", raw_text or ""))
    if not cleaned.strip():
        return ""
    first_body_idx = len(cleaned)
    for marker in ("{", "```"):
        idx = cleaned.find(marker)
        if idx != -1 and idx < first_body_idx:
            first_body_idx = idx
    sent_m = _SENTINEL_HEADER_RE.search(cleaned)
    if sent_m and sent_m.start() < first_body_idx:
        first_body_idx = sent_m.start()
    close_m = _ORPHAN_CLOSE_THINK_RE.match(cleaned[:first_body_idx])
    if close_m:
        cleaned = trim(cleaned[close_m.end() :])
    cleaned = trim(_UNCLOSED_OPEN_THINK_TO_FENCE_RE.sub("", cleaned))
    return cleaned if cleaned.strip() else ""


def _is_choice_like_dict(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and bool(obj)
        and ("label" in obj or "text" in obj)
        and set(obj.keys()).issubset(_CHOICE_ONLY_KEYS)
    )


def _coerce_repaired_to_dict(candidate: Any) -> dict | None:
    """Coerce a parsed or json_repair-salvaged dict/list into a single JSON object dict."""
    if isinstance(candidate, dict):
        return candidate if candidate else None
    if not isinstance(candidate, list):
        return None

    top_dicts: list[dict[str, Any]] = []
    bare_choices: list[dict[str, Any]] = []
    for item in candidate:
        if isinstance(item, dict) and item:
            if _is_choice_like_dict(item):
                bare_choices.append(item)
            else:
                top_dicts.append(item)
        elif isinstance(item, list):
            for sub in item:
                if _is_choice_like_dict(sub):
                    bare_choices.append(sub)

    if top_dicts:
        merged: dict[str, Any] = {}
        for d in top_dicts:
            for k, v in d.items():
                if k not in merged or merged[k] in ("", None, [], {}):
                    merged[k] = v
                elif (
                    k in ("outcome_narrative", "next_narrative", "narrative")
                    and isinstance(merged[k], str)
                    and isinstance(v, str)
                    and v.startswith(merged[k])
                    and len(v) > len(merged[k])
                ):
                    merged[k] = v
        if bare_choices and "next_choices" not in merged and "choices" not in merged:
            merged["next_choices"] = bare_choices
        return merged if merged else None

    if bare_choices:
        return {"next_choices": bare_choices} if len(bare_choices) > 1 else bare_choices[0]
    return None


def _try_parse_json_or_repair(text_block: str) -> dict | None:
    """Attempt strict json.loads followed by json_repair, coercing list salvage results to dict."""
    if not text_block:
        return None
    try:
        parsed = _coerce_repaired_to_dict(json.loads(text_block))
        if parsed is not None:
            return parsed
    except Exception:
        pass
    try:
        repaired = json_repair.repair_json(text_block, return_objects=True)
        return _coerce_repaired_to_dict(repaired)
    except Exception:
        return None


def _extract_json(raw: str) -> dict:
    """Models sometimes wrap JSON in markdown fences, prepend thinking tags,
    add trailing self-correction meta-commentary, or use unescaped quotes.
    Extracts the authentic clean JSON payload with multi-tier parsing."""
    text = _strip_reasoning_blocks(raw.strip())

    # 1. Try markdown code fences ```json ... ``` in order
    fence_matches = _JSON_FENCE_RE.findall(text)
    for fence in fence_matches:
        parsed = _try_parse_json_or_repair(fence.strip())
        if parsed is not None:
            return parsed

    # Strip unclosed leading/trailing markdown fences from truncated stream outputs
    unfenced = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    unfenced = re.sub(r"\s*```\s*$", "", unfenced).strip()

    # 2. Try raw unfenced text as direct JSON
    try:
        parsed = _coerce_repaired_to_dict(json.loads(unfenced))
        if parsed is not None:
            return parsed
    except Exception:
        pass

    # 3. Find top-level balanced {...} blocks and salvage single or split blocks
    # (Prevents trailing meta-commentary like '** (Wait - correcting...)' from corrupting the valid primary block)
    balanced_blocks = _find_balanced_json_blocks(unfenced)
    parsed_blocks: list[dict[str, Any]] = []
    for block in balanced_blocks:
        parsed_block = _try_parse_json_or_repair(block)
        if parsed_block is not None:
            parsed_blocks.append(parsed_block)
    if parsed_blocks:
        if len(parsed_blocks) == 1:
            return parsed_blocks[0]
        merged_blocks = _coerce_repaired_to_dict(parsed_blocks)
        if merged_blocks is not None:
            return merged_blocks
        return parsed_blocks[0]

    # 4. Outermost {...} block parse (fallback if brace balancing had syntax errors)
    start, end = unfenced.find("{"), unfenced.rfind("}")
    if start != -1 and end != -1 and end > start:
        parsed = _try_parse_json_or_repair(unfenced[start : end + 1])
        if parsed is not None:
            return parsed

    # 5. Last resort: json_repair on full unfenced / original text
    for candidate_text in (unfenced, text):
        if not candidate_text:
            continue
        try:
            repaired = json_repair.repair_json(candidate_text, return_objects=True)
            parsed = _coerce_repaired_to_dict(repaired)
            if parsed is not None:
                return parsed
        except Exception:
            pass

    raise ValueError(f"LLM did not return parseable JSON:\n{raw[:800]}")


def _is_sentinel_narration_model(
    response_model: Type[BaseModel] | None, output_protocol: str | None = None
) -> bool:
    if output_protocol == "sentinel":
        return True
    if output_protocol == "json":
        return False
    return getattr(response_model, "__name__", "") in (
        "DeterministicTurnNarration",
        "DeterministicCombatNarration",
    )


def _is_refusal_or_junk_prose(text: str) -> bool:
    cleaned = (text or "").strip()
    if len(cleaned) < 80:
        return True
    if cleaned.lstrip().startswith(("{", "[")):
        return True
    if _REFUSAL_PROSE_RE.search(cleaned):
        return True
    sentences = len(re.findall(r"[.!?。！？]", cleaned))
    if sentences < 2 and len(cleaned) < 160:
        return True
    return False


def _strip_wrapping_quotes(val: Any) -> str:
    s = str(val or "").strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    return s


def _parse_sentinel_choice_line(line: str) -> dict[str, Any] | None:
    item = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", (line or "").strip()).strip()
    if not item or (item.startswith("(") and item.endswith(")")):
        return None
    item = re.sub(r"\[\s*([a-zA-Z_]+\s*=[^\]]+?)\s*\]", r"\1", item)
    parts = [p.strip() for p in item.split("|")]
    if len(parts) == 1:
        lbl = _strip_wrapping_quotes(parts[0])
        return {"label": lbl, "stat": "NONE", "requirement": 0} if lbl else None

    seg0 = parts[0].upper().strip("[] ")
    if seg0 not in _SENTINEL_STAT_SET:
        lbl = _strip_wrapping_quotes(" | ".join(parts))
        return {"label": lbl, "stat": "NONE", "requirement": 0} if lbl else None

    stat = "NONE" if seg0 == "FREE" else seg0
    req = 0 if stat in ("NONE", "ITEM") else 6
    opt_start = 1
    dc_m = re.match(
        r"^(?:(?:DC|REQ|REQUIREMENT)\s*[:=]?\s*)?(\d{1,2})$", parts[1].strip("[] "), re.IGNORECASE
    )
    if dc_m:
        req = max(0, min(15, int(dc_m.group(1))))
        opt_start = 2
    if stat == "NONE":
        req = 0

    choice_obj: dict[str, Any] = {"stat": stat, "requirement": req}
    label_parts: list[str] = []
    for seg in parts[opt_start:]:
        clean_seg = seg.strip().strip("[]").strip()
        kv_m = re.match(
            r"^(ends_dialogue|dismisses_npc|topic_id|category|target|target_npc|intent|sub_intent|mp_cost|gold_spent|dc|req|requirement|quest_id|stat)\s*=\s*(.+)$",
            clean_seg,
            re.IGNORECASE,
        )
        dc_colon_m = (
            None
            if kv_m
            else re.match(r"^(?:dc|req(?:uirement)?)\s*[:=]\s*(\d{1,2})$", clean_seg, re.IGNORECASE)
        )
        if kv_m:
            k = kv_m.group(1).lower()
            v = _strip_wrapping_quotes(kv_m.group(2))
            if k in (
                "ends_dialogue",
                "dismisses_npc",
                "topic_id",
                "category",
                "intent",
                "sub_intent",
                "quest_id",
                "stat",
            ):
                v = v.strip("\"'").strip()
            if k in ("ends_dialogue", "dismisses_npc"):
                choice_obj[k] = v.lower() in ("true", "1", "yes")
            elif k in ("mp_cost", "gold_spent"):
                try:
                    choice_obj[k] = max(0, int(float(v)))
                except (TypeError, ValueError):
                    pass
            elif k in ("dc", "req", "requirement"):
                try:
                    choice_obj["requirement"] = (
                        0 if choice_obj["stat"] == "NONE" else max(0, min(15, int(float(v))))
                    )
                except (TypeError, ValueError):
                    pass
            elif k == "stat":
                up_s = v.upper()
                if up_s in _SENTINEL_STAT_SET:
                    choice_obj["stat"] = "NONE" if up_s == "FREE" else up_s
                    if choice_obj["stat"] == "NONE":
                        choice_obj["requirement"] = 0
            elif k in ("target", "target_npc"):
                if v and v.lower() not in ("none", "null"):
                    choice_obj["target_npc"] = v
            elif v and v.lower() not in ("none", "null"):
                choice_obj[k] = v
        elif dc_colon_m:
            choice_obj["requirement"] = (
                0 if choice_obj["stat"] == "NONE" else max(0, min(15, int(dc_colon_m.group(1))))
            )
        elif seg:
            label_parts.append(seg)

    label = _strip_wrapping_quotes(" | ".join(label_parts))
    if not label:
        return None
    choice_obj["label"] = label
    return choice_obj


def _parse_sentinel_meta_line(line: str, meta_out: dict[str, Any]) -> None:
    cleaned = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", (line or "").strip()).strip()
    if not cleaned or (cleaned.startswith("(") and cleaned.endswith(")")):
        return
    if ":" not in cleaned:
        return
    key, val = cleaned.split(":", 1)
    k_low = key.strip().lower()
    v_str = val.strip()
    if not v_str:
        return

    if k_low in ("memory", "episodic_memory"):
        if v_str.lower() not in ("none", "null", "n/a", "routine"):
            meta_out["episodic_memory"] = v_str[:300]
        return

    if k_low in ("pose", "actor_pose"):
        parts = [p.strip() for p in v_str.split("|")]
        actor = parts[0] if parts else ""
        if actor and actor.lower() not in ("none", "null"):
            pose_dict: dict[str, str] = {}
            if len(parts) > 1 and parts[1] and parts[1].lower() not in ("none", "null"):
                pose_dict["posture"] = parts[1][:100]
            if len(parts) > 2 and parts[2] and parts[2].lower() not in ("none", "null"):
                pose_dict["holding"] = parts[2][:100]
            if pose_dict:
                meta_out["actor_poses"][actor] = pose_dict
        return

    if k_low in ("cast", "cast_event"):
        parts = [p.strip() for p in v_str.split("|")]
        if len(parts) < 2:
            return
        ev_type = parts[0].lower()
        npc = parts[1]
        if ev_type not in ("arrive", "depart", "engage") or not npc:
            return
        gender: str | None = None
        descriptor = ""
        reason = ""
        if len(parts) >= 3 and parts[2].lower() in ("male", "female", "non-binary", "other", "m", "f"):
            g_low = parts[2].lower()
            gender = {"m": "male", "f": "female"}.get(g_low, g_low)
            descriptor = parts[3] if len(parts) > 3 else ""
            reason = parts[4] if len(parts) > 4 else ""
        else:
            reason = parts[2] if len(parts) > 2 else ""
            descriptor = parts[3] if len(parts) > 3 else ""
        ev: dict[str, Any] = {"type": ev_type, "npc": npc, "reason": reason}
        if gender:
            ev["gender"] = gender
        if descriptor:
            ev["descriptor"] = descriptor
        meta_out["cast_events"].append(ev)
        return

    if k_low in ("epistemic", "epistemic_signal"):
        parts = [p.strip() for p in v_str.split("|")]
        pos_parts: list[str] = []
        ep_extra: dict[str, str] = {}
        for p_seg in parts:
            ep_kv = re.match(
                r"^(kind|confidence|category|proof_ref)\s*=\s*(.+)$", p_seg, re.IGNORECASE
            )
            if ep_kv:
                ep_extra[ep_kv.group(1).lower()] = ep_kv.group(2).strip().strip('"')
            else:
                pos_parts.append(p_seg)
        if len(pos_parts) >= 2 and pos_parts[0]:
            sig: dict[str, Any] = {
                "target_npc": pos_parts[0],
                "fact_key": pos_parts[1] if len(pos_parts) > 1 else "",
                "summary": pos_parts[2] if len(pos_parts) > 2 else "",
                "proof_ref": ep_extra.get("proof_ref") or (pos_parts[3] if len(pos_parts) > 3 else ""),
            }
            if "kind" in ep_extra:
                sig["kind"] = ep_extra["kind"]
            elif len(pos_parts) > 4 and pos_parts[4]:
                sig["kind"] = pos_parts[4]
            if "confidence" in ep_extra:
                sig["confidence"] = ep_extra["confidence"]
            if "category" in ep_extra:
                sig["category"] = ep_extra["category"]
            meta_out["epistemic_signal"].append(sig)


def _parse_sentinel_narration(text: str) -> dict[str, Any] | None:
    work = text.strip()
    if re.match(r"^\s*```", work):
        work = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*\n?", "", work, flags=re.IGNORECASE)
    work = re.sub(r"\n?\s*```\s*$", "", work).strip()

    matches = list(_SENTINEL_HEADER_RE.finditer(work))
    if not matches:
        return None

    scene_title = ""
    outcome_parts: list[str] = []
    next_parts: list[str] = []
    choices_list: list[dict[str, Any]] = []
    meta_out: dict[str, Any] = {
        "episodic_memory": None,
        "actor_poses": {},
        "cast_events": [],
        "epistemic_signal": [],
    }

    for idx, m in enumerate(matches):
        tag = m.group(1).upper()
        inline_rest = (m.group(2) or "").strip()
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(work)
        body = re.sub(r"\n?\s*```\s*$", "", work[m.end() : end_pos]).strip()

        if tag == "TITLE":
            if inline_rest:
                scene_title = inline_rest.strip(" \"'*#")[:120]
                if body:
                    outcome_parts.append(body)
            else:
                raw_lines = body.splitlines()
                non_empty_idx = next((i for i, ln in enumerate(raw_lines) if ln.strip()), None)
                if non_empty_idx is not None:
                    scene_title = raw_lines[non_empty_idx].strip().strip(" \"'*#")[:120]
                    rem_body = "\n".join(raw_lines[non_empty_idx + 1 :]).strip()
                    if rem_body:
                        outcome_parts.append(rem_body)
        elif tag in ("OUTCOME", "OUTCOME_NARRATIVE"):
            combined = (
                f"{inline_rest}\n{body}".strip() if (inline_rest and body) else (body or inline_rest)
            )
            if combined:
                outcome_parts.append(combined)
        elif tag in ("NEXT", "NEXT_NARRATIVE"):
            combined = (
                f"{inline_rest}\n{body}".strip() if (inline_rest and body) else (body or inline_rest)
            )
            if combined:
                next_parts.append(combined)
        elif tag in ("CHOICES", "NEXT_CHOICES"):
            combined = (
                f"{inline_rest}\n{body}".strip() if (inline_rest and body) else (body or inline_rest)
            )
            for line in combined.splitlines():
                parsed_c = _parse_sentinel_choice_line(line)
                if parsed_c is not None:
                    choices_list.append(parsed_c)
        elif tag == "META":
            combined = (
                f"{inline_rest}\n{body}".strip() if (inline_rest and body) else (body or inline_rest)
            )
            for line in combined.splitlines():
                _parse_sentinel_meta_line(line, meta_out)

    outcome_narrative = "\n\n".join(p for p in outcome_parts if p).strip()
    next_narrative = "\n\n".join(p for p in next_parts if p).strip()
    if not outcome_narrative and next_narrative:
        outcome_narrative = next_narrative
        next_narrative = ""
    if not outcome_narrative and not next_narrative:
        return None

    return {
        "scene_title": scene_title,
        "outcome_narrative": outcome_narrative,
        "next_narrative": next_narrative,
        "next_choices": choices_list,
        "cast_events": meta_out["cast_events"],
        "actor_poses": meta_out["actor_poses"],
        "episodic_memory": meta_out["episodic_memory"],
        "epistemic_signal": meta_out["epistemic_signal"],
    }


def _extract_sentinel_or_json(raw: str, response_model: Type[BaseModel] | None = None) -> dict:
    """Parse Sentinel-delimited narration first, falling back transparently to JSON or clean story prose."""
    cleaned = _strip_reasoning_blocks((raw or "").strip())
    if not cleaned:
        raise ValueError("LLM returned empty response after stripping reasoning blocks.")

    sentinel_res = _parse_sentinel_narration(cleaned)
    if sentinel_res is not None:
        return sentinel_res

    # Backward-compatible JSON path (for models/mocks that still output JSON)
    if "{" in cleaned:
        try:
            return _extract_json(raw)
        except Exception:
            pass

    # Untagged prose salvage with refusal/junk rejection
    if _is_refusal_or_junk_prose(cleaned):
        raise ValueError(f"LLM did not return valid narration or sentinel sections:\n{raw[:800]}")

    paras = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if len(paras) >= 2:
        outcome_narrative = "\n\n".join(paras[:-1])
        next_narrative = paras[-1]
    else:
        outcome_narrative = cleaned
        next_narrative = ""
    return {
        "scene_title": "",
        "outcome_narrative": outcome_narrative,
        "next_narrative": next_narrative,
        "next_choices": [],
        "cast_events": [],
        "actor_poses": {},
        "episodic_memory": None,
        "epistemic_signal": [],
    }


def _is_sentinel_complete(
    raw_text: str,
    finish_reason: str | None,
    response_model: Type[BaseModel] | None = None,
) -> bool:
    if not raw_text or not raw_text.strip():
        return False
    cleaned = _strip_reasoning_blocks(raw_text.strip())
    if not cleaned:
        return False
    # If model fell back to JSON, apply strict JSON completeness rules
    stripped_lead = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).lstrip()
    if stripped_lead.startswith("{") and not _SENTINEL_HEADER_RE.search(cleaned):
        return _is_response_complete(raw_text, finish_reason, response_model=response_model)
    if finish_reason != "length":
        return True
    # Hit token limit: complete if @@CHOICES / @@META already arrived, or combat @@NEXT ended cleanly
    headers = [m.group(1).upper() for m in _SENTINEL_HEADER_RE.finditer(cleaned)]
    if any(h in ("CHOICES", "NEXT_CHOICES", "META") for h in headers):
        return True
    if getattr(response_model, "__name__", "") == "DeterministicCombatNarration" and any(
        h in ("NEXT", "NEXT_NARRATIVE") for h in headers
    ):
        if re.search(r'[.!?。！？]["\'\)\]]*\s*$', cleaned):
            return True
    return False


def _normalize_truncated_prefix(raw_text: str) -> str:
    """Trim trailing unclosed fence markers and dangling escape backslashes before auto-continuation."""
    cleaned = re.sub(
        r"\s*```(?:json|markdown|md|text|txt)?\s*$", "", raw_text or "", flags=re.IGNORECASE
    ).rstrip()
    trailing_slashes = len(cleaned) - len(cleaned.rstrip("\\"))
    if trailing_slashes % 2 == 1:
        cleaned = cleaned[:-1]
    return cleaned


def _is_response_complete(
    raw_text: str,
    finish_reason: str | None,
    response_model: Type[BaseModel] | None = None,
    required_any_keys: list[list[str]] | None = None,
) -> bool:
    if not raw_text or not raw_text.strip():
        return False  # Explicit empty / blank guard
    clean = raw_text.strip()
    clean = re.sub(r"```(?:json)?\s*$", "", clean).strip()  # triple-backtick fence strip

    if finish_reason == "length":
        if not clean.endswith("}") and not clean.endswith("]"):
            return False
        # Check if the JSON is actually already complete without repair (e.g. trailing whitespace/newlines after valid JSON)
        try:
            stripped = _strip_reasoning_blocks(clean)
            candidate_strs = [f.strip() for f in _JSON_FENCE_RE.findall(stripped) if f.strip()]
            if not candidate_strs:
                unfenced = re.sub(r"^\s*```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
                unfenced = re.sub(r"\s*```\s*$", "", unfenced).strip()
                candidate_strs = [unfenced]
            for cand in candidate_strs:
                try:
                    parsed = json.loads(cand)
                except Exception:
                    continue
                if isinstance(parsed, dict) and parsed:
                    if required_any_keys:
                        for key_group in required_any_keys:
                            if not any(k in parsed for k in key_group):
                                return False
                    if response_model:
                        response_model.model_validate(parsed)
                    return True
        except Exception:
            return False
        return False

    if not clean.endswith("}") and not clean.endswith("]"):
        return False
    return True
