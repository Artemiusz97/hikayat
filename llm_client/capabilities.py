"""Model candidate routing, capability caches, error classification, backoff, and probing."""
from __future__ import annotations

import asyncio
import random
from typing import Any

from openai import (
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

from config import (
    LLM_FALLBACK_MODELS,
    LLM_MODEL,
    LLM_SUPPRESS_NARRATION_COT,
    LLM_THINKING_MAX_TOKENS,
    NSFW_LLM_FALLBACK_MODELS,
    NSFW_LLM_MODEL,
)
from .state import (
    _client,
    _is_live_llm_blocked,
    _nsfw_client,
    _prioritize_healthy_candidates,
    _semaphore,
    _unwrap_live_llm_blocked,
    log,
)

_MODEL_CAPABILITIES: dict[str, dict] = {}
_STREAM_USAGE_UNSUPPORTED: set[tuple[str, str]] = set()
_REASONING_PARAM_UNSUPPORTED: set[tuple[str, str]] = set()
_PENALTY_PARAM_UNSUPPORTED: set[tuple[str, str]] = set()
_PREFILL_UNSUPPORTED: set[tuple[str, str]] = set()
_COT_SUPPRESS_UNSUPPORTED: set[tuple[str, str]] = set()


def get_candidate_models(
    is_nsfw: bool = False, use_utility: bool = False
) -> list[tuple[AsyncOpenAI, str]]:
    """Return a list of (client, model_name) tuples to try in priority order.

    NSFW scenarios cascade only within NSFW models:
      [(nsfw_client, NSFW_LLM_MODEL), (nsfw_client, nsfw_fallback_1), ...]
      — never crosses over into the standard (potentially censored) model.

    Standard scenarios cascade only within standard models:
      [(default_client, LLM_MODEL), (default_client, fallback_1), ...]

    If is_nsfw=True but no NSFW client is configured, falls back to the standard
    chain as a last resort (i.e. NSFW credentials are simply not set up yet).
    Guarantees no duplicate (client, model_name) pairs and places healthy models
    ahead of any model currently on circuit-breaker cooldown.
    """
    candidates = []
    seen = set()

    from config import LLM_UTILITY_MODEL, NSFW_LLM_UTILITY_MODEL

    if is_nsfw and _nsfw_client and NSFW_LLM_MODEL:
        # NSFW chain: primary NSFW model + NSFW fallbacks only.
        target_model = (NSFW_LLM_UTILITY_MODEL if use_utility else NSFW_LLM_MODEL) or NSFW_LLM_MODEL
        if target_model and target_model.strip():
            nsfw_pair_key = (id(_nsfw_client), target_model.strip())
            candidates.append((_nsfw_client, target_model.strip()))
            seen.add(nsfw_pair_key)

        for fb_model in NSFW_LLM_FALLBACK_MODELS:
            fb = fb_model.strip()
            if fb:
                pair_key = (id(_nsfw_client), fb)
                if pair_key not in seen:
                    candidates.append((_nsfw_client, fb))
                    seen.add(pair_key)

        if candidates:
            return _prioritize_healthy_candidates(candidates)

    # Standard chain (also used when NSFW credentials are not configured).
    target_model = (LLM_UTILITY_MODEL if use_utility else LLM_MODEL) or LLM_MODEL
    if target_model and target_model.strip():
        std_pair_key = (id(_client), target_model.strip())
        candidates.append((_client, target_model.strip()))
        seen.add(std_pair_key)

    for fb_model in LLM_FALLBACK_MODELS:
        fb = fb_model.strip()
        if fb:
            pair_key = (id(_client), fb)
            if pair_key not in seen:
                candidates.append((_client, fb))
                seen.add(pair_key)

    return _prioritize_healthy_candidates(candidates)


def is_nsfw_configured() -> bool:
    """Return True if separate NSFW credentials and model are configured."""
    return _nsfw_client is not None and bool(NSFW_LLM_MODEL)


def get_probe_candidate_groups() -> dict[str, list[dict]]:
    """Return configured standard and NSFW candidate models for diagnostic probing."""
    from config import LLM_UTILITY_MODEL, NSFW_LLM_UTILITY_MODEL

    std_models: list[dict] = []
    seen_std = set()

    if LLM_MODEL and LLM_MODEL.strip():
        m = LLM_MODEL.strip()
        std_models.append({"client": _client, "model": m, "role": "Primary"})
        seen_std.add(m)

    for fb in LLM_FALLBACK_MODELS:
        m = fb.strip()
        if m and m not in seen_std:
            std_models.append({"client": _client, "model": m, "role": "Fallback"})
            seen_std.add(m)

    if LLM_UTILITY_MODEL and LLM_UTILITY_MODEL.strip():
        m = LLM_UTILITY_MODEL.strip()
        if m not in seen_std:
            std_models.append({"client": _client, "model": m, "role": "Utility"})
            seen_std.add(m)

    nsfw_models: list[dict] = []
    seen_nsfw = set()

    if _nsfw_client and NSFW_LLM_MODEL and NSFW_LLM_MODEL.strip():
        m = NSFW_LLM_MODEL.strip()
        nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Primary"})
        seen_nsfw.add(m)

        for fb in NSFW_LLM_FALLBACK_MODELS:
            m = fb.strip()
            if m and m not in seen_nsfw:
                nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Fallback"})
                seen_nsfw.add(m)

        if NSFW_LLM_UTILITY_MODEL and NSFW_LLM_UTILITY_MODEL.strip():
            m = NSFW_LLM_UTILITY_MODEL.strip()
            if m not in seen_nsfw:
                nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Utility"})
                seen_nsfw.add(m)

    return {
        "standard": std_models,
        "nsfw": nsfw_models,
    }


def _is_reasoning_model(model_name: str) -> bool:
    """Return True for hybrid thinking/reasoning models whose thought tokens share max_tokens."""
    lower_m = (model_name or "").lower().strip()
    if lower_m in ("o1", "o3", "o4"):
        return True
    return any(
        marker in lower_m
        for marker in (
            "gemma-4",
            "gemma4",
            "deepseek-r1",
            "reasoner",
            "qwq",
            "thinking",
            "/o1",
            "-o1",
            "o1-",
            "/o3",
            "-o3",
            "o3-",
            "/o4",
            "-o4",
            "o4-",
        )
    )


def _effective_json_max_tokens(
    model_name: str,
    requested_max_tokens: int,
    *,
    use_utility: bool = False,
    suppress_cot: bool = False,
) -> int:
    req = int(requested_max_tokens or 3500)
    if use_utility and 0 < req <= 2500:
        if suppress_cot or not _is_reasoning_model(model_name):
            return max(128, req)
        cap = 2048 if req <= 1000 else 3500
        return max(req, min(cap, int(LLM_THINKING_MAX_TOKENS)))
    floor = LLM_THINKING_MAX_TOKENS if _is_reasoning_model(model_name) else 3500
    return max(req, int(floor))


def _is_openai_official(base_url: str) -> bool:
    return "api.openai.com" in (base_url or "").lower()


def _model_supports_json_schema(base_url: str, model_name: str) -> bool:
    if not _is_openai_official(base_url):
        return False
    lower_m = (model_name or "").lower()
    return "gemma" not in lower_m


def _model_supports_json_mode(base_url: str, model_name: str) -> bool:
    lower_m = (model_name or "").lower()
    # Gemma models on third-party endpoints (like Nano-GPT / vLLM / Outlines) have a known bug
    # where tokenizer control tokens generate infinite whitespace loops under constrained json_object mode.
    if "gemma" in lower_m and not _is_openai_official(base_url):
        return False
    return True


def _is_non_retriable_error(e: Exception) -> bool:
    """Return True if the error indicates a fatal configuration/auth issue that cannot succeed on retry."""
    if _unwrap_live_llm_blocked(e) is not None or isinstance(e, (AuthenticationError, NotFoundError)):
        return True
    if isinstance(e, BadRequestError):
        err_msg = str(e).lower()
        if any(
            marker in err_msg
            for marker in (
                "invalid model",
                "does not exist",
                "context length",
                "maximum context",
                "not found",
            )
        ):
            return True
    return False


def _is_model_overloaded_error(e: Exception) -> bool:
    """Return True if a 429/API error indicates the upstream model is overloaded or out of quota and should fast-failover."""
    err_msg = str(e).lower()
    if any(
        marker in err_msg
        for marker in (
            "model_overloaded",
            "temporarily overloaded",
            "choose another model",
            "daily_rpd_limit_exceeded",
            "insufficient_quota",
        )
    ):
        return True
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err_dict = body.get("error") if isinstance(body.get("error"), dict) else body
        code = str(err_dict.get("code") or "").lower()
        if code in ("model_overloaded", "daily_rpd_limit_exceeded", "insufficient_quota"):
            return True
    return False


def _extract_retry_after(error: Exception | None) -> float | None:
    """Extract Retry-After delay (in seconds) from an HTTP error response if present and reasonable."""
    if error is None:
        return None
    resp = getattr(error, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else getattr(error, "headers", None)
    if not headers or not hasattr(headers, "get"):
        return None
    raw = (
        headers.get("retry-after")
        or headers.get("Retry-After")
        or headers.get("x-ratelimit-reset-requests")
    )
    if raw is None:
        return None
    try:
        val = float(raw)
        if 0.0 < val <= 30.0:
            return val
    except (ValueError, TypeError):
        pass
    return None


async def _backoff_sleep(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 5.0,
    error: Exception | None = None,
) -> None:
    """Sleep with exponential backoff and randomized jitter to prevent rate-limit contention."""
    if isinstance(error, RateLimitError):
        base_delay = max(base_delay, 2.5)
        max_delay = max(max_delay, 8.0)
    retry_after = _extract_retry_after(error)
    if retry_after is not None:
        delay = min(max(max_delay, 15.0), retry_after + random.uniform(0.1, 0.5))
    else:
        delay = min(max_delay, base_delay * (2**attempt) + random.uniform(0.1, 0.6))
    log.info(
        "LLM transient failure; backing off for %.2fs before retry (attempt %d)...",
        delay,
        attempt + 1,
    )
    await asyncio.sleep(delay)


def _should_suppress_cot(
    suppress_cot: bool | None,
    is_sentinel: bool,
    use_utility: bool,
    max_tokens: int,
) -> bool:
    if not LLM_SUPPRESS_NARRATION_COT:
        return False
    if suppress_cot is not None:
        return bool(suppress_cot)
    return bool(is_sentinel or (use_utility and int(max_tokens or 0) <= 2000))


def _strip_unsupported_bad_request_params(
    err: Exception,
    kwargs: dict[str, Any],
    cache_key: tuple[str, str],
    model_name: str,
    requested_max_tokens: int,
) -> bool:
    """Strip unsupported reasoning/max_tokens/extra_body overrides after a provider 400 error; return True if kwargs changed."""
    if _unwrap_live_llm_blocked(err) is not None:
        return False
    err_str = str(err).lower()
    changed = False
    if "extra_body" in kwargs and any(
        marker in err_str
        for marker in (
            "chat_template_kwargs",
            "enable_thinking",
            "extra_body",
            "unknown field",
            "extra inputs",
            "unrecognized",
            "unexpected keyword",
        )
    ):
        log.info(
            "Model '%s' rejected CoT suppression extra_body; caching bypass for endpoint.",
            model_name,
        )
        _COT_SUPPRESS_UNSUPPORTED.add(cache_key)
        kwargs.pop("extra_body", None)
        if _is_reasoning_model(model_name) and int(kwargs.get("max_tokens") or 0) < 2048:
            kwargs["max_tokens"] = min(2048, int(LLM_THINKING_MAX_TOKENS))
        changed = True
    if ("reasoning_effort" in err_str or "reasoning" in err_str) and "reasoning_effort" in kwargs:
        log.info("Model '%s' does not support reasoning_effort; bypassing.", model_name)
        _REASONING_PARAM_UNSUPPORTED.add(cache_key)
        kwargs.pop("reasoning_effort", None)
        changed = True
    mentions_other_param = any(
        p in err_str for p in ("response_format", "response format", "stream_options")
    )
    penalty_markers = (
        ("presence_penalty", "frequency_penalty", "penalty")
        if mentions_other_param
        else (
            "presence_penalty",
            "frequency_penalty",
            "penalty",
            "unknown field",
            "extra inputs",
            "unrecognized",
            "unexpected keyword",
            "unsupported",
        )
    )
    if ("presence_penalty" in kwargs or "frequency_penalty" in kwargs) and any(
        marker in err_str for marker in penalty_markers
    ):
        log.info(
            "Model '%s' rejected presence/frequency penalty; stripping for retry and caching bypass.",
            model_name,
        )
        _PENALTY_PARAM_UNSUPPORTED.add(cache_key)
        kwargs.pop("presence_penalty", None)
        kwargs.pop("frequency_penalty", None)
        changed = True
    if (
        any(
            marker in err_str
            for marker in ("max_tokens", "context_length", "context length", "maximum context")
        )
        and int(kwargs.get("max_tokens") or 0) > 3500
    ):
        clamped = min(int(requested_max_tokens or 3500), 3500)
        log.info(
            "Clamping max_tokens for '%s' from %s to %d after provider rejection.",
            model_name,
            kwargs.get("max_tokens"),
            clamped,
        )
        kwargs["max_tokens"] = clamped
        changed = True
    return changed


async def probe_model_capabilities(client: AsyncOpenAI, model_name: str) -> dict:
    """Test if a model supports native JSON mode (response_format) and basic completions."""
    cache_key = (str(getattr(client, "base_url", "")), model_name)
    if cache_key in _MODEL_CAPABILITIES:
        return _MODEL_CAPABILITIES[cache_key]
    if model_name in _MODEL_CAPABILITIES:
        return _MODEL_CAPABILITIES[model_name]

    base_url = str(getattr(client, "base_url", ""))
    can_json_mode = _model_supports_json_mode(base_url, model_name)
    can_json_schema = _model_supports_json_schema(base_url, model_name)
    info = {
        "model": model_name,
        "json_mode": can_json_mode,
        "json_schema": can_json_schema,
        "status": "unknown",
        "error": None,
    }
    async with _semaphore:
        try:
            if can_json_mode:
                await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": 'Return JSON: {"status": "ok"}'}],
                    response_format={"type": "json_object"},
                    max_tokens=60,
                    timeout=15.0,
                )
            else:
                await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": 'Return JSON: {"status": "ok"}'}],
                    max_tokens=60,
                    timeout=15.0,
                )
            info["status"] = "ok"
        except Exception as e:
            err_msg = str(e).lower()
            if "response_format" in err_msg or "response format" in err_msg:
                info["json_mode"] = False
                info["json_schema"] = False
                # Cache negative capability immediately so response_format is never attempted
                _MODEL_CAPABILITIES[cache_key] = dict(info)
                _MODEL_CAPABILITIES[model_name] = dict(info)
                try:
                    await client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": 'Return JSON: {"status": "ok"}'}],
                        max_tokens=60,
                        timeout=15.0,
                    )
                    info["status"] = "ok"
                except Exception as e2:
                    info["status"] = "error"
                    info["error"] = str(e2)
            else:
                info["status"] = "error"
                info["error"] = str(e)

    if info.get("status") == "ok":
        _MODEL_CAPABILITIES[cache_key] = info
        _MODEL_CAPABILITIES[model_name] = info
    return info


async def probe_all_configured_models(quiet: bool = False) -> dict[str, dict]:
    """Pre-probe all configured standard and NSFW candidate models to warm capability caches."""
    if _is_live_llm_blocked():
        return {}
    groups = get_probe_candidate_groups()
    probed_results = {}

    for group_name, candidates in groups.items():
        for item in candidates:
            client = item["client"]
            model_name = item["model"]
            role = item["role"]
            role_tag = f" ({role})" if role != "Primary" else ""
            cache_key = (str(getattr(client, "base_url", "")), model_name)

            if cache_key in _MODEL_CAPABILITIES:
                cap = _MODEL_CAPABILITIES[cache_key]
            else:
                try:
                    cap = await probe_model_capabilities(client, model_name)
                except Exception as e:
                    cap = {
                        "model": model_name,
                        "json_mode": False,
                        "status": "error",
                        "error": str(e),
                    }

            probed_results[f"{group_name}:{model_name}"] = cap
            if not quiet:
                if cap.get("json_mode"):
                    log.info(
                        "[LLM Probe] %s model '%s'%s: Native JSON mode supported.",
                        group_name.capitalize(),
                        model_name,
                        role_tag,
                    )
                elif cap.get("status") == "ok":
                    log.info(
                        "[LLM Probe] %s model '%s'%s: Native JSON mode UNSUPPORTED (using markdown JSON fallback).",
                        group_name.capitalize(),
                        model_name,
                        role_tag,
                    )
                else:
                    log.warning(
                        "[LLM Probe] %s model '%s'%s: Probe warning/error: %s",
                        group_name.capitalize(),
                        model_name,
                        role_tag,
                        cap.get("error"),
                    )

    return probed_results
