"""Batch JSON, Sentinel narration, raw text, and vector embedding LLM transport calls."""
from __future__ import annotations

import re
import time
from typing import Any, Type

from openai import APITimeoutError, BadRequestError, RateLimitError
from pydantic import BaseModel

from config import (
    EMBEDDING_MODEL,
    LLM_REASONING_EFFORT,
    LLM_REQUEST_TIMEOUT,
    LLM_TEMPERATURE,
    NSFW_LLM_TEMPERATURE,
)
from .capabilities import (
    _COT_SUPPRESS_UNSUPPORTED,
    _MODEL_CAPABILITIES,
    _PENALTY_PARAM_UNSUPPORTED,
    _PREFILL_UNSUPPORTED,
    _REASONING_PARAM_UNSUPPORTED,
    _backoff_sleep,
    _effective_json_max_tokens,
    _is_model_overloaded_error,
    _is_non_retriable_error,
    _model_supports_json_mode,
    _model_supports_json_schema,
    _should_suppress_cot,
    _strip_unsupported_bad_request_params,
    get_candidate_models,
)
from .parsing import (
    _extract_json,
    _extract_sentinel_or_json,
    _is_response_complete,
    _is_sentinel_complete,
    _is_sentinel_narration_model,
    _normalize_truncated_prefix,
    _strip_reasoning_blocks,
)
from .state import (
    LiveLLMBlockedError,
    _ACTIVE_LLM_HANDLER,
    _ACTIVE_SAMPLING_PROFILE,
    _IN_STREAM_CALL,
    _append_llm_tape_entry,
    _embed_client,
    _extract_cached_tokens,
    _semaphore,
    _telemetry_totals,
    _unwrap_live_llm_blocked,
    log,
    record_llm_telemetry,
    trip_model_circuit,
)
from .streaming import _build_messages


async def get_embedding(text: str) -> list[float]:
    """Fetch vector embedding for semantic search."""
    if not text or not text.strip():
        return []
    handler = _ACTIVE_LLM_HANDLER.get()
    if handler is not None:
        try:
            res = await handler(call_kind="embedding", text=text)
            vec = list(res) if isinstance(res, list) else []
            _append_llm_tape_entry("embedding", ok=True, result=vec)
            return vec
        except Exception as e:
            _append_llm_tape_entry("embedding", ok=False, exc=e)
            log.warning(f"Intercepted embedding failed for model {EMBEDDING_MODEL}: {e}")
            return []
    try:
        # Replace newlines as recommended by OpenAI for embeddings
        clean_text = text.replace("\n", " ")
        async with _semaphore:
            response = await _embed_client.embeddings.create(
                model=EMBEDDING_MODEL, input=clean_text
            )
        vec = response.data[0].embedding
        _append_llm_tape_entry("embedding", ok=True, result=vec)
        return vec
    except Exception as e:
        _append_llm_tape_entry("embedding", ok=False, exc=e)
        if _unwrap_live_llm_blocked(e) is not None:
            log.debug("Blocked live embedding call in test mode: %s", e)
        else:
            log.warning(f"Embedding failed for model {EMBEDDING_MODEL}: {e}")
        return []


async def call_llm_json(
    system_prompt: str | list,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
    required_any_keys: list[list[str]] | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
    output_protocol: str | None = None,
    suppress_cot: bool | None = None,
) -> dict:
    """Call the LLM and parse a structured dict out of the response with automatic retries and failover."""
    record_tape = not _IN_STREAM_CALL.get()
    handler = _ACTIVE_LLM_HANDLER.get()
    try:
        if handler is not None:
            res = await handler(
                call_kind="json",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
                is_nsfw=is_nsfw,
                use_utility=use_utility,
                timeout=timeout,
                required_any_keys=required_any_keys,
                response_model=response_model,
                system_zones=system_zones,
            )
            if record_tape:
                _append_llm_tape_entry("json", response_model=response_model, ok=True, result=res)
            return res
        res = await _call_llm_json_live(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=retries,
            is_nsfw=is_nsfw,
            use_utility=use_utility,
            timeout=timeout,
            required_any_keys=required_any_keys,
            response_model=response_model,
            system_zones=system_zones,
            output_protocol=output_protocol,
            suppress_cot=suppress_cot,
        )
        if record_tape:
            _append_llm_tape_entry("json", response_model=response_model, ok=True, result=res)
        return res
    except BaseException as exc:
        if record_tape and isinstance(exc, Exception):
            _append_llm_tape_entry("json", response_model=response_model, ok=False, exc=exc)
        raise


async def call_llm_narrator(
    system_prompt: str | list,
    user_prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    timeout: float | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """Generate turn narration using the Sentinel-delimited protocol with JSON fallback."""
    return await call_llm_json(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        is_nsfw=is_nsfw,
        use_utility=False,
        timeout=timeout,
        response_model=response_model,
        system_zones=system_zones,
        output_protocol="sentinel",
        suppress_cot=True,
    )


async def _call_llm_json_live(
    system_prompt: str | list,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
    required_any_keys: list[list[str]] | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
    output_protocol: str | None = None,
    suppress_cot: bool | None = None,
) -> dict:
    sampling_profile = _ACTIVE_SAMPLING_PROFILE.get() if not use_utility else None
    if temperature is None:
        if sampling_profile and "temperature" in sampling_profile:
            temperature = float(sampling_profile["temperature"])
        else:
            temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE
    live_pres_penalty = (
        float(sampling_profile.get("presence_penalty", 0.2)) if sampling_profile else 0.2
    )
    live_freq_penalty = (
        float(sampling_profile.get("frequency_penalty", 0.2)) if sampling_profile else 0.2
    )

    is_sentinel = _is_sentinel_narration_model(response_model, output_protocol=output_protocol)
    req_timeout = timeout if timeout is not None else LLM_REQUEST_TIMEOUT
    last_err = None

    async with _semaphore:
        candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)
        for cand_idx, (client, model_name) in enumerate(candidates):
            if cand_idx > 0:
                _telemetry_totals["fallback_activations"] = (
                    int(_telemetry_totals.get("fallback_activations", 0) or 0) + 1
                )
            last_validation_feedback: tuple[str, str] | None = None
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    base_url = str(getattr(client, "base_url", ""))
                    cache_key = (base_url, model_name)
                    want_suppress_cot = (
                        _should_suppress_cot(suppress_cot, is_sentinel, use_utility, max_tokens)
                        and cache_key not in _COT_SUPPRESS_UNSUPPORTED
                    )
                    req_max_tokens = _effective_json_max_tokens(
                        model_name,
                        max_tokens,
                        use_utility=use_utility,
                        suppress_cot=want_suppress_cot,
                    )
                    base_messages = _build_messages(
                        system_prompt,
                        user_prompt,
                        base_url=base_url,
                        model_name=model_name,
                        system_zones=system_zones,
                    )
                    attempt_messages = list(base_messages)
                    if attempt > 0 and last_validation_feedback is not None:
                        bad_snip, err_hint = last_validation_feedback
                        correction_prompt = (
                            f"Your previous output was invalid ({err_hint[:240]}). "
                            "Respond using exact @@TITLE:, @@OUTCOME, @@NEXT, and @@CHOICES sections with raw story prose and NO JSON or markdown code fences."
                            if is_sentinel
                            else f"Your previous output failed JSON validation ({err_hint[:240]}). "
                            "Output ONLY a single valid JSON object starting with '{' and ending with '}' matching the required schema."
                        )
                        attempt_messages.extend(
                            [
                                {"role": "assistant", "content": bad_snip[:600]},
                                {"role": "user", "content": correction_prompt},
                            ]
                        )

                    kwargs: dict[str, Any] = {
                        "model": model_name,
                        "temperature": temperature,
                        "max_tokens": req_max_tokens,
                        "messages": list(attempt_messages),
                        "timeout": req_timeout,
                    }
                    if not use_utility and cache_key not in _PENALTY_PARAM_UNSUPPORTED:
                        kwargs["presence_penalty"] = live_pres_penalty
                        kwargs["frequency_penalty"] = live_freq_penalty
                    if LLM_REASONING_EFFORT and cache_key not in _REASONING_PARAM_UNSUPPORTED:
                        kwargs["reasoning_effort"] = LLM_REASONING_EFFORT
                    if want_suppress_cot:
                        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

                    def _sync_attempt_timeout() -> None:
                        if timeout is None:
                            return
                        rem_t = float(req_timeout) - (time.perf_counter() - t0)
                        if rem_t <= 0.5:
                            raise TimeoutError("Request timed out.")
                        kwargs["timeout"] = max(2.0, rem_t)

                    known_cap = _MODEL_CAPABILITIES.get(cache_key) or _MODEL_CAPABILITIES.get(
                        model_name
                    )
                    supports_json_mode = (
                        False
                        if is_sentinel
                        else (
                            known_cap.get("json_mode", _model_supports_json_mode(base_url, model_name))
                            if known_cap
                            else _model_supports_json_mode(base_url, model_name)
                        )
                    )
                    supports_json_schema = (
                        False
                        if is_sentinel
                        else (
                            (
                                known_cap.get(
                                    "json_schema",
                                    _model_supports_json_schema(base_url, model_name),
                                )
                                if known_cap
                                else _model_supports_json_schema(base_url, model_name)
                            )
                            and supports_json_mode
                        )
                    )
                    response = None

                    if response_model and supports_json_schema:
                        for _schema_try in range(2):
                            try:
                                _sync_attempt_timeout()
                                schema_kwargs = kwargs.copy()
                                schema_kwargs["response_format"] = {
                                    "type": "json_schema",
                                    "json_schema": {
                                        "name": response_model.__name__,
                                        "schema": response_model.model_json_schema(),
                                        "strict": True,
                                    },
                                }
                                response = await client.chat.completions.create(**schema_kwargs)
                                cap_record = (
                                    dict(known_cap)
                                    if known_cap
                                    else {
                                        "model": model_name,
                                        "json_mode": True,
                                        "status": "ok",
                                        "error": None,
                                    }
                                )
                                cap_record["json_schema"] = True
                                _MODEL_CAPABILITIES[cache_key] = cap_record
                                _MODEL_CAPABILITIES[model_name] = cap_record
                                break
                            except (RateLimitError, APITimeoutError, TimeoutError):
                                raise
                            except Exception as e:
                                if _strip_unsupported_bad_request_params(
                                    e, kwargs, cache_key, model_name, max_tokens
                                ):
                                    continue
                                if _is_non_retriable_error(e):
                                    raise
                                log.warning(
                                    "Model '%s' strict json_schema failed (%s), caching unsupported and falling back to json_object...",
                                    model_name,
                                    type(e).__name__,
                                )
                                cap_record = (
                                    dict(known_cap)
                                    if known_cap
                                    else {
                                        "model": model_name,
                                        "json_mode": supports_json_mode,
                                        "status": "ok",
                                        "error": None,
                                    }
                                )
                                cap_record["json_schema"] = False
                                _MODEL_CAPABILITIES[cache_key] = cap_record
                                _MODEL_CAPABILITIES[model_name] = cap_record
                                supports_json_schema = False
                                response = None
                                break

                    if not response and supports_json_mode:
                        for _mode_try in range(3):
                            try:
                                _sync_attempt_timeout()
                                response = await client.chat.completions.create(
                                    response_format={"type": "json_object"}, **kwargs
                                )
                                if (
                                    model_name not in _MODEL_CAPABILITIES
                                    and cache_key not in _MODEL_CAPABILITIES
                                ):
                                    cap_record = {
                                        "model": model_name,
                                        "json_mode": True,
                                        "status": "ok",
                                        "error": None,
                                    }
                                    _MODEL_CAPABILITIES[cache_key] = cap_record
                                    _MODEL_CAPABILITIES[model_name] = cap_record
                                break
                            except (RateLimitError, APITimeoutError, TimeoutError):
                                raise
                            except Exception as e:
                                if _strip_unsupported_bad_request_params(
                                    e, kwargs, cache_key, model_name, max_tokens
                                ):
                                    continue
                                if _is_non_retriable_error(e):
                                    raise
                                err_str = str(e).lower()
                                if "response_format" in err_str or "response format" in err_str:
                                    log.info(
                                        "Model '%s' does not support response_format={'type': 'json_object'}; bypassing in future calls.",
                                        model_name,
                                    )
                                    cap_record = {
                                        "model": model_name,
                                        "json_mode": False,
                                        "json_schema": False,
                                        "status": "ok",
                                        "error": None,
                                    }
                                    _MODEL_CAPABILITIES[cache_key] = cap_record
                                    _MODEL_CAPABILITIES[model_name] = cap_record
                                    supports_json_mode = False
                                    break
                                if "presence_penalty" in kwargs or "frequency_penalty" in kwargs:
                                    _PENALTY_PARAM_UNSUPPORTED.add(cache_key)
                                    kwargs.pop("presence_penalty", None)
                                    kwargs.pop("frequency_penalty", None)
                                    continue
                                raise

                    used_prefill = False
                    if not response:
                        if (
                            not is_sentinel
                            and not supports_json_mode
                            and cache_key not in _PREFILL_UNSUPPORTED
                        ):
                            used_prefill = True
                            kwargs["messages"] = list(attempt_messages) + [
                                {"role": "assistant", "content": "{"}
                            ]

                    raw = ""
                    continuation_count = 0
                    usage_obj = None
                    elapsed_ms = 0

                    while continuation_count <= 2:
                        if not response:
                            while True:
                                try:
                                    _sync_attempt_timeout()
                                    response = await client.chat.completions.create(**kwargs)
                                    break
                                except BadRequestError as bad_req_err:
                                    if continuation_count > 0:
                                        log.warning(
                                            "Batch auto-continuation (pass %d) rejected with BadRequestError: %s. Salvaging accumulated text...",
                                            continuation_count,
                                            bad_req_err,
                                        )
                                        response = None
                                        break
                                    if _strip_unsupported_bad_request_params(
                                        bad_req_err, kwargs, cache_key, model_name, max_tokens
                                    ):
                                        continue
                                    if used_prefill and not _is_non_retriable_error(bad_req_err):
                                        log.info(
                                            "Model '%s' rejected assistant '{' prefill; disabling prefill for endpoint.",
                                            model_name,
                                        )
                                        _PREFILL_UNSUPPORTED.add(cache_key)
                                        used_prefill = False
                                        kwargs["messages"] = list(attempt_messages)
                                        continue
                                    if (
                                        "presence_penalty" in kwargs
                                        or "frequency_penalty" in kwargs
                                    ) and not _is_non_retriable_error(bad_req_err):
                                        _PENALTY_PARAM_UNSUPPORTED.add(cache_key)
                                        kwargs.pop("presence_penalty", None)
                                        kwargs.pop("frequency_penalty", None)
                                        continue
                                    raise
                        if response is None:
                            break
                        if not response.choices:
                            raise ValueError(
                                f"LLM provider returned an empty response (no choices) for model '{model_name}'."
                            )

                        choice = response.choices[0]
                        cont_raw = choice.message.content or ""
                        if used_prefill and continuation_count == 0 and cont_raw:
                            cleaned_cont = _strip_reasoning_blocks(cont_raw)
                            unfenced_cont = re.sub(
                                r"^\s*```(?:json|markdown|md|text|txt)?\s*",
                                "",
                                cleaned_cont,
                                flags=re.IGNORECASE,
                            ).lstrip()
                            if unfenced_cont and not unfenced_cont.startswith("{"):
                                cont_raw = "{" + unfenced_cont
                        if continuation_count > 0:
                            cont_raw = re.sub(
                                r"^\s*```(?:json|markdown|md|text|txt)?\s*",
                                "",
                                cont_raw,
                                flags=re.IGNORECASE,
                            )
                        raw += cont_raw

                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        if getattr(response, "usage", None):
                            if usage_obj is None:
                                usage_obj = type(
                                    "Usage",
                                    (),
                                    {
                                        "prompt_tokens": 0,
                                        "completion_tokens": 0,
                                        "prompt_tokens_details": None,
                                    },
                                )()
                            usage_obj.prompt_tokens += (
                                getattr(response.usage, "prompt_tokens", 0) or 0
                            )
                            usage_obj.completion_tokens += (
                                getattr(response.usage, "completion_tokens", 0) or 0
                            )
                            cached = _extract_cached_tokens(response.usage)
                            if cached is not None:
                                if usage_obj.prompt_tokens_details is None:
                                    usage_obj.prompt_tokens_details = {"cached_tokens": 0}
                                usage_obj.prompt_tokens_details["cached_tokens"] += cached

                        is_done_now = (
                            _is_sentinel_complete(
                                raw, choice.finish_reason, response_model=response_model
                            )
                            if is_sentinel
                            else _is_response_complete(
                                raw,
                                choice.finish_reason,
                                response_model=response_model,
                                required_any_keys=required_any_keys,
                            )
                        )
                        if is_done_now:
                            break

                        if continuation_count >= 2:
                            log.warning(
                                "Max auto-continuations reached, proceeding with potentially truncated output."
                            )
                            break

                        clean_raw_for_context = _normalize_truncated_prefix(
                            re.sub(r"(\n\s*){4,}", "\n", raw)
                        )
                        if not clean_raw_for_context:
                            log.warning(
                                "LLM model '%s' output yielded no visible content; skipping empty continuation.",
                                model_name,
                            )
                            break

                        raw = clean_raw_for_context
                        continuation_count += 1
                        log.warning(
                            f"LLM model '{model_name}' output was truncated. Attempting auto-continuation (pass {continuation_count})..."
                        )

                        cont_instruction = (
                            "Your previous response was cut off. Continue EXACTLY where you left off in the exact same @@ section format without repeating earlier text or adding markdown fences."
                            if is_sentinel
                            else "Your previous response was cut off. Please continue EXACTLY where you left off, do not repeat yourself, do not output any markdown formatting or introductory text, just the raw JSON continuation."
                        )
                        cont_messages = list(attempt_messages) + [
                            {"role": "assistant", "content": clean_raw_for_context},
                            {"role": "user", "content": cont_instruction},
                        ]
                        kwargs["messages"] = cont_messages
                        response = None

                    try:
                        result = (
                            _extract_sentinel_or_json(raw, response_model=response_model)
                            if is_sentinel
                            else _extract_json(raw)
                        )
                    except Exception as salvage_err:
                        last_validation_feedback = (raw[:600], str(salvage_err))
                        raise ValueError(
                            f"LLM model '{model_name}' output was unparseable after {continuation_count} continuations."
                        ) from salvage_err

                    if not isinstance(result, dict) or not result:
                        last_validation_feedback = (raw[:600], "Empty or non-object JSON payload.")
                        raise ValueError(
                            f"LLM model '{model_name}' did not return a valid structured object."
                        )

                    if required_any_keys:
                        for key_group in required_any_keys:
                            if not any(k in result for k in key_group):
                                miss_msg = f"JSON missing required fields from group {key_group}."
                                last_validation_feedback = (raw[:600], miss_msg)
                                raise ValueError(f"LLM model '{model_name}' {miss_msg}")

                    if response_model:
                        try:
                            validated = response_model.model_validate(result)
                            record_llm_telemetry(
                                model_name, elapsed_ms, usage=usage_obj, success=True
                            )
                            return validated.model_dump(exclude_unset=False)
                        except Exception as val_e:
                            last_validation_feedback = (raw[:600], str(val_e))
                            raise ValueError(
                                f"LLM output failed Pydantic validation for model '{model_name}': {val_e}"
                            )

                    record_llm_telemetry(model_name, elapsed_ms, usage=usage_obj, success=True)
                    return result
                except LiveLLMBlockedError:
                    raise
                except Exception as e:
                    if (blocked := _unwrap_live_llm_blocked(e)) is not None:
                        raise blocked
                    last_err = e
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(
                        model_name, elapsed_ms, usage=None, success=False, error=str(e)
                    )
                    log.warning(
                        "LLM model '%s' attempt %d/%d failed: %s",
                        model_name,
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    if _is_non_retriable_error(e) or _is_model_overloaded_error(e):
                        log.warning(
                            "Encountered non-retriable or overloaded error (%s). Cascading immediately to next candidate...",
                            type(e).__name__,
                        )
                        break
                    if attempt < retries:
                        await _backoff_sleep(attempt, error=e)

            if retries > 0:
                trip_model_circuit(model_name)
            if cand_idx + 1 < len(candidates):
                log.warning(
                    "All attempts for model '%s' failed. Cascading to next fallback candidate...",
                    model_name,
                )
            else:
                log.warning(
                    "All attempts for model '%s' failed (no further fallback candidates configured).",
                    model_name,
                )

    raise RuntimeError(
        f"All LLM candidate models in fallback chain failed. Last error: {last_err}"
    ) from last_err


async def call_llm_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int = 1024,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
) -> str:
    """Call the LLM and return the raw string content of the response with automatic retries and failover."""
    handler = _ACTIVE_LLM_HANDLER.get()
    if handler is not None:
        try:
            res = await handler(
                call_kind="text",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
                is_nsfw=is_nsfw,
                use_utility=use_utility,
                timeout=timeout,
            )
            text_res = str(res) if res is not None else ""
            _append_llm_tape_entry("text", ok=True, result=text_res)
            return text_res
        except Exception as e:
            _append_llm_tape_entry("text", ok=False, exc=e)
            log.error("All candidate LLM models failed for intercepted call_llm_text: %s", e)
            return ""
    res = await _call_llm_text_live(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        is_nsfw=is_nsfw,
        use_utility=use_utility,
        timeout=timeout,
    )
    _append_llm_tape_entry("text", ok=True, result=res)
    return res


async def _call_llm_text_live(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int = 1024,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
) -> str:
    if temperature is None:
        temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE

    req_timeout = timeout if timeout is not None else LLM_REQUEST_TIMEOUT
    last_err = None

    async with _semaphore:
        candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)
        for cand_idx, (client, model_name) in enumerate(candidates):
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        timeout=req_timeout,
                    )
                    if not response.choices:
                        raise ValueError(
                            f"LLM text model '{model_name}' returned empty choices."
                        )
                    content = response.choices[0].message.content or ""
                    if not content.strip():
                        raise ValueError(
                            f"LLM text model '{model_name}' returned empty content."
                        )
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(
                        model_name,
                        elapsed_ms,
                        usage=getattr(response, "usage", None),
                        success=True,
                    )
                    return content
                except LiveLLMBlockedError as e:
                    log.debug("Blocked live LLM text call in test mode: %s", e)
                    return ""
                except Exception as e:
                    if (blocked := _unwrap_live_llm_blocked(e)) is not None:
                        log.debug("Blocked live LLM text call in test mode: %s", blocked)
                        return ""
                    last_err = e
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(
                        model_name, elapsed_ms, usage=None, success=False, error=str(e)
                    )
                    log.warning(
                        "LLM text model '%s' attempt %d/%d failed: %s",
                        model_name,
                        attempt + 1,
                        retries + 1,
                        e,
                    )
                    if _is_non_retriable_error(e) or _is_model_overloaded_error(e):
                        log.warning(
                            "Encountered non-retriable or overloaded error (%s). Cascading immediately to next candidate...",
                            type(e).__name__,
                        )
                        break
                    if attempt < retries:
                        await _backoff_sleep(attempt, error=e)

            if retries > 0:
                trip_model_circuit(model_name)
            if cand_idx + 1 < len(candidates):
                log.warning(
                    "All attempts for text model '%s' failed. Cascading to next candidate...",
                    model_name,
                )
            else:
                log.warning(
                    "All attempts for text model '%s' failed (no further fallback candidates configured).",
                    model_name,
                )

    if last_err:
        log.error("All candidate LLM models failed for call_llm_text: %s", last_err)
    return ""
