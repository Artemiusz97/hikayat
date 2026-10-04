"""
Optional scene-image generation via ImageRouter (https://imagerouter.io),
which exposes an OpenAI-images-compatible endpoint in front of many
different image models -- including Flux variants. Swap IMAGE_ROUTER_MODEL
(or pass model= explicitly) to point at whatever model slug you want; check
https://imagerouter.io/models for the current catalog since slugs change as
models are added.

This is intentionally decoupled from the LLM client so you can point it at
a totally different provider later without touching game_engine.py.
"""
import asyncio
import logging
import aiohttp

from config import IMAGE_ROUTER_API_KEY, IMAGE_ROUTER_BASE_URL, IMAGE_ROUTER_MODEL

logger = logging.getLogger("hikayat.image_client")


class ImageGenError(Exception):
    pass


async def generate_scene_image(prompt: str, model: str | None = None) -> str:
    """Returns a hosted image URL, or raises ImageGenError."""
    if not IMAGE_ROUTER_API_KEY:
        raise ImageGenError("IMAGE_ROUTER_API_KEY is not set in .env")

    target_model = model or IMAGE_ROUTER_MODEL
    payload = {
        "prompt": prompt[:2000],
        "model": target_model,
        "quality": "auto",
        "size": "auto",
        "response_format": "url",
        "output_format": "webp",
    }
    headers = {
        "Authorization": f"Bearer {IMAGE_ROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(IMAGE_ROUTER_BASE_URL, json=payload, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=60)) as resp:
                logger.info("HTTP Request: POST %s (model=%s) \"HTTP/%s.%s %s %s\"",
                            IMAGE_ROUTER_BASE_URL, target_model,
                            resp.version.major, resp.version.minor, resp.status, resp.reason)
                try:
                    body = await resp.json(content_type=None)
                except Exception:
                    raw_text = await resp.text()
                    raise ImageGenError(f"Image API returned non-JSON (HTTP {resp.status}): {raw_text[:300]}")
                if resp.status >= 400:
                    raise ImageGenError(f"ImageRouter error {resp.status}: {body}")
                try:
                    return body["data"][0]["url"]
                except (KeyError, IndexError, TypeError):
                    raise ImageGenError(f"Unexpected ImageRouter response shape: {body}")
    except ImageGenError:
        raise
    except asyncio.TimeoutError as e:
        raise ImageGenError(f"Image generation timed out after 60s ({IMAGE_ROUTER_BASE_URL})") from e
    except aiohttp.ClientError as e:
        raise ImageGenError(f"Image generation HTTP client error: {e}") from e
