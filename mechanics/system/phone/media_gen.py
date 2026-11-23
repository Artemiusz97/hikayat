from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Mapping, Optional

import db
import image_client
from mechanics.combat.items import (
    is_digital_item,
    parse_digital_item_metadata,
    update_digital_media_image,
)
from mechanics.narrative.image_prompt_composer import compose_phone_media_prompt

log = logging.getLogger("hikayat.phone.media_gen")

_IN_FLIGHT_MEDIA_ITEMS: set[int] = set()
_BACKGROUND_MEDIA_TASKS: set[asyncio.Task[Any]] = set()


def is_media_item_in_flight(item_id: int) -> bool:
    """Returns True if an async image generation task is currently running for item_id."""
    try:
        return int(item_id) in _IN_FLIGHT_MEDIA_ITEMS
    except (TypeError, ValueError):
        return False


def spawn_phone_media_image_task(
    session_id: int,
    user_id: int,
    item_id: int,
    *,
    auto_trigger: bool = True,
    force_regenerate: bool = False,
    broadcast_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> asyncio.Task[dict[str, Any]]:
    """Schedules phone media image generation with strong task tracking."""
    task = asyncio.create_task(
        generate_phone_media_image(
            session_id,
            user_id,
            item_id,
            auto_trigger=auto_trigger,
            force_regenerate=force_regenerate,
            broadcast_fn=broadcast_fn,
        )
    )
    _BACKGROUND_MEDIA_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_MEDIA_TASKS.discard)
    return task


async def drain_phone_media_tasks() -> None:
    """Waits for all tracked background phone media generation tasks to finish."""
    while _BACKGROUND_MEDIA_TASKS:
        pending = list(_BACKGROUND_MEDIA_TASKS)
        await asyncio.gather(*pending, return_exceptions=True)


def is_session_image_gen_enabled(session: Optional[Mapping[str, Any]], *, auto_only: bool = False) -> bool:
    """Returns True if image generation is active for this session."""
    if not isinstance(session, Mapping):
        return False
    mode = str(session.get("image_gen_enabled") or "0").strip().lower()
    if auto_only:
        return mode in ("1", "auto", "true")
    return mode in ("1", "2", "auto", "on_demand", "true")


async def _safe_broadcast(broadcast_fn: Optional[Callable[[dict[str, Any]], Any]], payload: dict[str, Any]) -> None:
    if not broadcast_fn:
        return
    try:
        res = broadcast_fn(payload)
        if hasattr(res, "__await__"):
            await res
    except Exception as exc:
        log.debug("Phone media broadcast failed: %s", exc)


async def generate_phone_media_image(
    session_id: int,
    user_id: int,
    item_id: int,
    *,
    auto_trigger: bool = False,
    force_regenerate: bool = False,
    broadcast_fn: Optional[Callable[[dict[str, Any]], Any]] = None,
) -> dict[str, Any]:
    """Generates and persists a portrait image for an NPC-sent smartphone digital media item."""
    clean_item_id = int(item_id)
    clean_user_id = int(user_id)
    clean_session_id = int(session_id)

    item = await db.adb(db.get_inventory_item_by_id, clean_item_id, clean_user_id)
    valid_digital_item = bool(item and is_digital_item(item))
    meta = dict(parse_digital_item_metadata(item) or {}) if valid_digital_item else {}
    existing_url = str(meta.get("image_url") or "").strip()

    async def _reset_stale_generating() -> None:
        if (
            valid_digital_item
            and meta.get("image_status") == "generating"
            and clean_item_id not in _IN_FLIGHT_MEDIA_ITEMS
        ):
            await db.adb(
                update_digital_media_image,
                clean_item_id,
                clean_user_id,
                image_status="ready" if existing_url else "idle",
            )

    session = await db.adb(db.get_session, clean_session_id)
    if not session:
        await _reset_stale_generating()
        return {"success": False, "reason": "session_not_found", "error": "Session not found"}

    if not valid_digital_item:
        return {"success": False, "reason": "media_not_found", "error": "Digital media item not found"}

    if not is_session_image_gen_enabled(session, auto_only=auto_trigger):
        await _reset_stale_generating()
        return {"success": False, "skipped": True, "reason": "image_gen_disabled"}

    if existing_url and not force_regenerate:
        if meta.get("image_status") != "ready":
            await db.adb(
                update_digital_media_image,
                clean_item_id,
                clean_user_id,
                image_status="ready",
            )
        return {
            "success": True,
            "media": {
                "id": item["id"],
                "name": item.get("name", ""),
                "contact_name": meta.get("contact_name") or "Subject",
                "contact_npc_id": meta.get("contact_npc_id") or "",
                "media_type": meta.get("media_type") or "photo",
                "caption": meta.get("caption") or "",
                "timestamp": meta.get("timestamp"),
                "tags": meta.get("tags") or [],
                "image_url": existing_url,
                "image_status": "ready",
            },
        }

    if clean_item_id in _IN_FLIGHT_MEDIA_ITEMS:
        return {
            "success": True,
            "in_flight": True,
            "media": {
                "id": item["id"],
                "name": item.get("name", ""),
                "contact_name": meta.get("contact_name") or "Subject",
                "contact_npc_id": meta.get("contact_npc_id") or "",
                "media_type": meta.get("media_type") or "photo",
                "caption": meta.get("caption") or "",
                "timestamp": meta.get("timestamp"),
                "tags": meta.get("tags") or [],
                "image_url": existing_url,
                "image_status": "generating",
            },
        }

    _IN_FLIGHT_MEDIA_ITEMS.add(clean_item_id)
    try:
        generating_media = await db.adb(
            update_digital_media_image,
            clean_item_id,
            clean_user_id,
            image_status="generating",
        )
        await _safe_broadcast(
            broadcast_fn,
            {
                "type": "PHONE_MEDIA_IMAGE",
                "session_id": clean_session_id,
                "item_id": clean_item_id,
                "image_url": existing_url,
                "image_status": "generating",
                "media_type": meta.get("media_type") or "photo",
            },
        )

        contact_lookup = str(meta.get("contact_npc_id") or meta.get("contact_name") or "").strip()
        contact = None
        if contact_lookup:
            char_row = await db.adb(db.get_character, clean_user_id, session_id=clean_session_id)
            char_id = int(char_row.get("id", 0)) if isinstance(char_row, dict) else 0
            contact = await db.adb(db.get_contact, clean_session_id, contact_lookup, character_id=char_id)
            if not contact and meta.get("contact_name") and meta.get("contact_name") != contact_lookup:
                contact = await db.adb(db.get_contact, clean_session_id, meta["contact_name"], character_id=char_id)

        composed = compose_phone_media_prompt(
            session,
            contact=contact,
            media_type=str(meta.get("media_type") or "photo"),
            caption=str(meta.get("caption") or item.get("name") or ""),
            contact_name=str(meta.get("contact_name") or ""),
        )

        settings_uid = session.get("host_user_id") or clean_user_id
        user_settings = await db.adb(db.get_settings, int(settings_uid)) if settings_uid else {}
        model_override = (user_settings or {}).get("image_model") or None

        image_res = await image_client.generate_scene_image(
            composed.prompt,
            model=model_override,
            session_id=clean_session_id,
            size=composed.size,
            negative_prompt=composed.negative_prompt,
        )
        local_web_url = str(getattr(image_res, "local_url", image_res) or "").strip()
        if not local_web_url:
            raise RuntimeError("Image generator returned an empty URL.")

        updated_media = await db.adb(
            update_digital_media_image,
            clean_item_id,
            clean_user_id,
            image_url=local_web_url,
            image_status="ready",
        )
        await _safe_broadcast(
            broadcast_fn,
            {
                "type": "PHONE_MEDIA_IMAGE",
                "session_id": clean_session_id,
                "item_id": clean_item_id,
                "image_url": local_web_url,
                "image_status": "ready",
                "media_type": meta.get("media_type") or "photo",
            },
        )
        return {"success": True, "media": updated_media or generating_media}
    except Exception as exc:
        log.warning("Failed to generate phone media image for item %s (session %s): %s", clean_item_id, clean_session_id, exc)
        failed_media = await db.adb(
            update_digital_media_image,
            clean_item_id,
            clean_user_id,
            image_status="error",
        )
        await _safe_broadcast(
            broadcast_fn,
            {
                "type": "PHONE_MEDIA_IMAGE",
                "session_id": clean_session_id,
                "item_id": clean_item_id,
                "image_url": existing_url,
                "image_status": "error",
                "media_type": meta.get("media_type") or "photo",
            },
        )
        return {"success": False, "error": str(exc), "media": failed_media}
    finally:
        _IN_FLIGHT_MEDIA_ITEMS.discard(clean_item_id)
