"""
Configuration loader.
All secrets come from environment variables / a local .env file (never hard-code keys).
"""
import os
from dotenv import load_dotenv

_IS_TEST_MODE = os.getenv("HIKAYAT_TEST_MODE", "").strip().lower() in ("1", "true", "yes")
if not _IS_TEST_MODE:
    load_dotenv()

APP_VERSION = "3.5.0"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Any OpenAI-compatible chat endpoint: OpenAI itself, OpenRouter, Groq, a local
# llama.cpp/vLLM/Ollama server, etc. Just point LLM_BASE_URL at it.
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# Optional: lightweight model for background utility tasks (e.g. Gemini Flash-Lite)
LLM_UTILITY_MODEL = os.getenv("LLM_UTILITY_MODEL", LLM_MODEL)
# Comma-separated list of fallback models for standard scenarios (e.g. "gpt-4o-mini,openrouter/auto")
LLM_FALLBACK_MODELS = [m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()]

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", LLM_BASE_URL)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", LLM_API_KEY)

# Optional: separate provider for NSFW scenarios (e.g. OpenRouter with a
# permissive open-weights model). When not set, NSFW scenarios fall back to
# the default LLM above — no hard failure.
NSFW_LLM_API_KEY = os.getenv("NSFW_LLM_API_KEY", "")
NSFW_LLM_BASE_URL = os.getenv("NSFW_LLM_BASE_URL", "")
NSFW_LLM_MODEL = os.getenv("NSFW_LLM_MODEL", "")
NSFW_LLM_UTILITY_MODEL = os.getenv("NSFW_LLM_UTILITY_MODEL", NSFW_LLM_MODEL)
# Comma-separated list of fallback models for NSFW scenarios
NSFW_LLM_FALLBACK_MODELS = [m.strip() for m in os.getenv("NSFW_LLM_FALLBACK_MODELS", "").split(",") if m.strip()]

# Per-request timeout (seconds) per attempt before switching to next fallback model
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "120.0"))

# Split streaming stall thresholds: generous TTFT for cold local KV prefill, fast inter-chunk stall detection
LLM_TTFT_TIMEOUT = float(os.getenv("LLM_TTFT_TIMEOUT", "75.0"))
LLM_CHUNK_IDLE_TIMEOUT = float(os.getenv("LLM_CHUNK_IDLE_TIMEOUT", "25.0"))

# Overall wall-clock deadline (seconds) across stream retries, continuations, and batch fallback per turn
LLM_STREAM_TOTAL_DEADLINE = float(os.getenv("LLM_STREAM_TOTAL_DEADLINE", "150.0"))

# Completion token ceiling for hybrid reasoning models (e.g. Gemma 4, DeepSeek-R1, QwQ)
LLM_THINKING_MAX_TOKENS = int(os.getenv("LLM_THINKING_MAX_TOKENS", "8192"))
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()
LLM_SUPPRESS_NARRATION_COT = os.getenv("LLM_SUPPRESS_NARRATION_COT", "true").lower() in ("true", "1", "yes")

# Dynamic multi-pass turn engine settings
ENABLE_DYNAMIC_MULTIPASS = os.getenv("ENABLE_DYNAMIC_MULTIPASS", "true").lower() in ("true", "1", "yes")
LLM_PASS1_TIMEOUT = float(os.getenv("LLM_PASS1_TIMEOUT", "45.0"))
LLM_PASS2_TIMEOUT = float(os.getenv("LLM_PASS2_TIMEOUT", str(LLM_REQUEST_TIMEOUT)))

# Sampling temperatures
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.85"))
NSFW_LLM_TEMPERATURE = float(os.getenv("NSFW_LLM_TEMPERATURE", "0.65"))

# Concurrency & connection security
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
LLM_VERIFY_SSL = os.getenv("LLM_VERIFY_SSL", "true").lower() in ("true", "1", "yes")

_old_db_path = "hikayat.db"
_new_db_path = os.path.join("data", "hikayat.db")
DB_PATH = os.getenv("DB_PATH", _old_db_path if os.path.exists(_old_db_path) else _new_db_path)


def _parse_channel_ids(env_val: str | None) -> set[int]:
    if not env_val:
        return set()
    result = set()
    for item in env_val.split(","):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


ALLOWED_CHANNEL_IDS = _parse_channel_ids(os.getenv("ALLOWED_CHANNEL_IDS"))
DISALLOWED_CHANNEL_IDS = _parse_channel_ids(os.getenv("DISALLOWED_CHANNEL_IDS"))


def is_channel_allowed(channel_id: int | None, parent_id: int | None = None) -> bool:
    """Check if a channel ID (or its parent channel ID if in a thread) is permitted.

    - If ALLOWED_CHANNEL_IDS is set, only those channel IDs are permitted.
    - If ALLOWED_CHANNEL_IDS is empty and DISALLOWED_CHANNEL_IDS is set, all channels except those are permitted.
    - If both are empty, all channels are permitted.
    """
    if channel_id is None:
        return True

    ids_to_check = {channel_id}
    if parent_id is not None:
        ids_to_check.add(parent_id)

    if ALLOWED_CHANNEL_IDS:
        return bool(ids_to_check & ALLOWED_CHANNEL_IDS)

    if DISALLOWED_CHANNEL_IDS:
        return not bool(ids_to_check & DISALLOWED_CHANNEL_IDS)

    return True


# ---------------------------------------------------------------- image gen
# Supports both cloud ImageRouter and local SD WebUI / Forge via /sdapi/v1/txt2img
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "imagerouter").lower().strip()

# Local SD WebUI / Forge settings
FORGE_BASE_URL = os.getenv("FORGE_BASE_URL", "http://127.0.0.1:7860").rstrip("/")
FORGE_STEPS = int(os.getenv("FORGE_STEPS", "20"))
FORGE_CFG_SCALE = float(os.getenv("FORGE_CFG_SCALE", "7.0"))
FORGE_SAMPLER = os.getenv("FORGE_SAMPLER", "Euler a").strip("\"'")

# Cloud ImageRouter settings
IMAGE_ROUTER_API_KEY = os.getenv("IMAGE_ROUTER_API_KEY", "")
IMAGE_ROUTER_BASE_URL = os.getenv("IMAGE_ROUTER_BASE_URL", "https://api.imagerouter.io/v1/openai/images/generations")
IMAGE_ROUTER_MODEL = os.getenv("IMAGE_ROUTER_MODEL", "black-forest-labs/flux-2-klein-9b")

# Directory where generated scene images are saved locally across both Discord & WebUI
GENERATED_IMAGES_DIR = os.getenv(
    "GENERATED_IMAGES_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "generated_images"))
)

# Drop-in directory for user-supplied custom fonts (.woff2, .woff, .ttf, .otf)
CUSTOM_FONTS_DIR = os.getenv(
    "CUSTOM_FONTS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "custom_fonts")),
)

if not _IS_TEST_MODE:
    os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)
    os.makedirs(CUSTOM_FONTS_DIR, exist_ok=True)


def validate_runtime_config(*, require_discord: bool = True, require_llm: bool = True) -> None:
    """Validate required runtime secrets and ensure runtime output directories exist."""
    missing: list[str] = []
    if require_discord and not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if require_llm and not LLM_API_KEY:
        missing.append("LLM_API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill it in."
        )
    os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)
    os.makedirs(CUSTOM_FONTS_DIR, exist_ok=True)
