import os
import json
import pytest
import discord
import httpx
from httpx import ASGITransport

import config
import db
import image_client
from image_client import GeneratedImage, save_image_bytes, download_and_save_image
from cogs.adventure.embeds import prepare_discord_image
from server import app


@pytest.fixture
def sample_image_bytes():
    # Minimal mock webp image header bytes
    return b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\xb0\x01\x00\x9d\x01*\x01\x00\x01\x00\x00"


@pytest.mark.asyncio
async def test_save_image_bytes_locally(sample_image_bytes):
    session_id = 887711
    generated = await save_image_bytes(sample_image_bytes, session_id=session_id, ext="webp")

    try:
        # 1. Returned object is a GeneratedImage and a subclass of str
        assert isinstance(generated, GeneratedImage)
        assert isinstance(generated, str)

        # 2. Path properties
        assert os.path.isabs(generated.local_path)
        assert os.path.exists(generated.local_path)
        assert os.path.dirname(generated.local_path) == config.GENERATED_IMAGES_DIR
        assert generated.filename.startswith(f"scene_{session_id}_")
        assert generated.local_url == f"/images/{generated.filename}"

        # 3. File content on disk matches saved bytes
        with open(generated.local_path, "rb") as f:
            disk_content = f.read()
        assert disk_content == sample_image_bytes

        # 4. JSON serialization compatibility
        payload = json.dumps({"image_url": generated})
        parsed = json.loads(payload)
        assert parsed["image_url"] == f"/images/{generated.filename}"

    finally:
        if os.path.exists(generated.local_path):
            os.remove(generated.local_path)


@pytest.mark.asyncio
async def test_discord_and_webui_shared_directory_resolution(sample_image_bytes):
    session_id = 998822
    generated = await save_image_bytes(sample_image_bytes, session_id=session_id, ext="webp")
    discord_file = None
    discord_file2 = None

    try:
        # Test Discord bot resolution from GeneratedImage instance
        embed_url, discord_file = prepare_discord_image(generated)
        assert embed_url == f"attachment://{generated.filename}"
        assert isinstance(discord_file, discord.File)
        assert discord_file.filename == generated.filename

        # Test Discord bot resolution from pure local URL string /images/{filename}
        local_url_str = f"/images/{generated.filename}"
        embed_url2, discord_file2 = prepare_discord_image(local_url_str)
        assert embed_url2 == f"attachment://{generated.filename}"
        assert isinstance(discord_file2, discord.File)
        assert discord_file2.filename == generated.filename

        # Test WebUI FastAPI static endpoint serving from the shared directory
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(f"/images/{generated.filename}")
            assert resp.status_code == 200
            assert resp.content == sample_image_bytes
            assert "image" in resp.headers.get("content-type", "")

    finally:
        if discord_file:
            discord_file.close()
        if discord_file2:
            discord_file2.close()
        if os.path.exists(generated.local_path):
            os.remove(generated.local_path)


@pytest.mark.asyncio
async def test_session_db_persistence_with_local_url(sample_image_bytes):
    user_id = 771122
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=True,
    )

    generated = await save_image_bytes(sample_image_bytes, session_id=session_id, ext="webp")
    discord_file = None

    try:
        # Update session with generated image (subclass of str)
        db.update_session(session_id, scene_image_url=generated)
        sess = db.get_session(session_id)
        assert sess["scene_image_url"] == f"/images/{generated.filename}"

        # Resolve for Discord from DB string
        embed_url, discord_file = prepare_discord_image(sess["scene_image_url"])
        assert embed_url == f"attachment://{generated.filename}"
        assert isinstance(discord_file, discord.File)

    finally:
        if discord_file:
            discord_file.close()
        if os.path.exists(generated.local_path):
            os.remove(generated.local_path)
