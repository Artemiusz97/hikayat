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
import base64
import logging
import os
import secrets
import time
import aiohttp

from config import (
    IMAGE_PROVIDER,
    FORGE_BASE_URL,
    FORGE_STEPS,
    FORGE_CFG_SCALE,
    FORGE_SAMPLER,
    IMAGE_ROUTER_API_KEY,
    IMAGE_ROUTER_BASE_URL,
    IMAGE_ROUTER_MODEL,
    GENERATED_IMAGES_DIR,
)

logger = logging.getLogger("hikayat.image_client")


class ImageGenError(Exception):
    pass


class GeneratedImage(str):
    """A string representing the local web URL (e.g. /images/scene_123.webp),
    with additional attributes for the absolute local file path and upstream remote URL."""
    local_path: str
    local_url: str
    remote_url: str
    filename: str

    def __new__(cls, local_url: str, local_path: str = "", remote_url: str = "", filename: str = ""):
        instance = super().__new__(cls, local_url)
        instance.local_path = local_path
        instance.local_url = local_url
        instance.remote_url = remote_url
        instance.filename = filename
        return instance


def _write_file_sync(path: str, data: bytes):
    with open(path, "wb") as f:
        f.write(data)


async def save_image_bytes(image_bytes: bytes, session_id: int | None = None, ext: str = "webp") -> GeneratedImage:
    """Saves raw image bytes directly to GENERATED_IMAGES_DIR and returns a GeneratedImage object."""
    os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)
    clean_sid = str(session_id) if session_id is not None else "gen"
    filename = f"scene_{clean_sid}_{int(time.time())}_{secrets.token_hex(4)}.{ext.lstrip('.')}"
    filepath = os.path.join(GENERATED_IMAGES_DIR, filename)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_file_sync, filepath, image_bytes)
    local_url = f"/images/{filename}"
    logger.info("Saved scene image locally: %s (%d bytes)", filepath, len(image_bytes))
    return GeneratedImage(local_url=local_url, local_path=filepath, remote_url="", filename=filename)


async def download_and_save_image(remote_url: str, session_id: int | None = None) -> GeneratedImage:
    """Downloads an image from remote_url, saves it locally in GENERATED_IMAGES_DIR,
    and returns a GeneratedImage instance."""
    if not remote_url or not isinstance(remote_url, str):
        raise ValueError("Invalid remote_url provided to download_and_save_image")

    # If it is already a local URL (e.g. /images/...)
    if remote_url.startswith("/images/"):
        fname = os.path.basename(remote_url)
        fpath = os.path.join(GENERATED_IMAGES_DIR, fname)
        return GeneratedImage(local_url=remote_url, local_path=fpath, remote_url="", filename=fname)

    os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)
    ext = "webp"
    url_path = remote_url.split("?")[0].lower()
    if url_path.endswith(".png"):
        ext = "png"
    elif url_path.endswith(".jpg") or url_path.endswith(".jpeg"):
        ext = "jpg"

    clean_sid = str(session_id) if session_id is not None else "gen"
    filename = f"scene_{clean_sid}_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
    filepath = os.path.join(GENERATED_IMAGES_DIR, filename)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(remote_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if content:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, _write_file_sync, filepath, content)
                        local_url = f"/images/{filename}"
                        logger.info("Downloaded and saved scene image locally: %s (%d bytes)", filepath, len(content))
                        return GeneratedImage(
                            local_url=local_url,
                            local_path=filepath,
                            remote_url=remote_url,
                            filename=filename,
                        )
                    else:
                        logger.warning("Downloaded image content from %s was empty", remote_url)
                else:
                    logger.warning("Failed to download image from %s (HTTP %s)", remote_url, resp.status)
    except Exception as e:
        logger.warning("Exception downloading image from %s: %s", remote_url, e)

    # Fallback to returning remote_url if local download failed
    return GeneratedImage(
        local_url=remote_url,
        local_path="",
        remote_url=remote_url,
        filename="",
    )


async def _generate_via_forge(
    prompt: str,
    negative_prompt: str | None = None,
    size: str = "auto",
    session_id: int | None = None,
    base_url: str | None = None,
) -> GeneratedImage:
    """Generates an image via a local SD WebUI / Forge instance (/sdapi/v1/txt2img)."""
    target_url = f"{(base_url or FORGE_BASE_URL).rstrip('/')}/sdapi/v1/txt2img"

    # Parse width and height from size string (e.g. "832x1216" -> w=832, h=1216)
    width, height = 1024, 1024
    if size and "x" in size:
        try:
            parts = size.lower().split("x")
            width, height = int(parts[0]), int(parts[1])
        except Exception:
            width, height = 1024, 1024

    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "width": width,
        "height": height,
        "steps": FORGE_STEPS,
        "cfg_scale": FORGE_CFG_SCALE,
        "sampler_name": FORGE_SAMPLER,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(target_url, json=payload, timeout=aiohttp.ClientTimeout(total=180)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ImageGenError(f"Forge API returned HTTP {resp.status}: {text[:300]}")
                data = await resp.json()
                images = data.get("images")
                if not images or not isinstance(images, list):
                    raise ImageGenError(f"Forge returned no images in response: {data}")

                raw_b64 = images[0]
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                raw_bytes = base64.b64decode(raw_b64)
                return await save_image_bytes(raw_bytes, session_id=session_id, ext="png")
    except aiohttp.ClientConnectorError as e:
        raise ImageGenError(
            f"Could not connect to Forge WebUI at {target_url}. "
            "Please ensure Forge is running on your PC with the '--api' flag enabled in webui-user.bat."
        ) from e
    except asyncio.TimeoutError as e:
        raise ImageGenError(f"Forge WebUI generation timed out after 180s ({target_url})") from e
    except ImageGenError:
        raise
    except Exception as e:
        raise ImageGenError(f"Forge generation failed: {e}") from e


async def generate_scene_image(
    prompt: str,
    model: str | None = None,
    session_id: int | None = None,
    size: str = "auto",
    negative_prompt: str | None = None,
) -> GeneratedImage:
    """Generates an image via local Forge WebUI or ImageRouter, saves it locally in GENERATED_IMAGES_DIR,
    and returns a GeneratedImage (a str representing the /images/... URL with local_path and remote_url attributes).
    Raises ImageGenError on generation failure."""
    # Check if routing to local Forge WebUI
    is_forge = (
        IMAGE_PROVIDER in ("forge", "sdwebui", "local")
        or (model and model.lower() in ("forge", "sdwebui", "local"))
        or (not IMAGE_ROUTER_API_KEY and FORGE_BASE_URL)
    )
    if is_forge:
        return await _generate_via_forge(
            prompt=prompt,
            negative_prompt=negative_prompt,
            size=size,
            session_id=session_id,
        )

    if not IMAGE_ROUTER_API_KEY:
        raise ImageGenError(
            "IMAGE_ROUTER_API_KEY is not set in .env. "
            "If using local Forge WebUI, set IMAGE_PROVIDER=forge in .env"
        )

    target_model = model or IMAGE_ROUTER_MODEL
    payload = {
        "prompt": prompt[:2000],
        "model": target_model,
        "quality": "auto",
        "size": size or "auto",
        "response_format": "url",
        "output_format": "webp",
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt[:1500]
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
                    data_entry = body["data"][0]
                except (KeyError, IndexError, TypeError):
                    raise ImageGenError(f"Unexpected ImageRouter response shape: {body}")

                if "b64_json" in data_entry:
                    raw_bytes = base64.b64decode(data_entry["b64_json"])
                    return await save_image_bytes(raw_bytes, session_id=session_id, ext="webp")

                remote_url = data_entry.get("url")
                if not remote_url:
                    raise ImageGenError(f"No image URL or b64_json in response: {data_entry}")

                saved = await download_and_save_image(remote_url, session_id=session_id)
                return saved

    except ImageGenError:
        raise
    except asyncio.TimeoutError as e:
        raise ImageGenError(f"Image generation timed out after 60s ({IMAGE_ROUTER_BASE_URL})") from e
    except aiohttp.ClientError as e:
        raise ImageGenError(f"Image generation HTTP client error: {e}") from e
