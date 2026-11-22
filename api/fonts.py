from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

import config

router = APIRouter()

# Mapping: extension -> (CSS @font-face format, MIME type, deduplication priority)
ALLOWED_FONT_EXTS: dict[str, tuple[str, str, int]] = {
    ".woff2": ("woff2", "font/woff2", 4),
    ".woff": ("woff", "font/woff", 3),
    ".otf": ("opentype", "font/otf", 2),
    ".ttf": ("truetype", "font/ttf", 1),
}

_WEIGHT_MAP: list[tuple[str, int]] = [
    ("extralight", 200),
    ("ultralight", 200),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("semibold", 600),
    ("demibold", 600),
    ("hairline", 100),
    ("thin", 100),
    ("light", 300),
    ("regular", 400),
    ("normal", 400),
    ("medium", 500),
    ("heavy", 800),
    ("black", 900),
    ("roman", 400),
    ("book", 400),
    ("bold", 700),
]

_VARIANT_TOKEN_RE = re.compile(
    r"(?:"
    r"[-_\s]+"
    r"(?i:"
    r"(?:extra|ultra)?(?:light|bold)|"
    r"(?:semi|demi)bold|"
    r"hairline|thin|regular|normal|book|roman|medium|heavy|black|"
    r"[1-9]00|"
    r"italic|oblique"
    r")+"
    r"|"
    r"(?<=[a-z0-9])"
    r"(?:"
    r"(?:Extra|Ultra)?(?:Light|Bold)|"
    r"(?:Semi|Demi)Bold|"
    r"Hairline|Thin|Regular|Medium|Italic|Oblique"
    r")+"
    r")$"
)


def _humanize_family_name(raw_name: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", raw_name)
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or raw_name.strip() or "Custom Font"


def parse_font_filename(filename: str) -> dict[str, Any]:
    """Parses a font filename into family metadata, CSS family identifier, weight, and style."""
    stem = Path(filename).stem
    lower_stem = stem.lower()

    style = "italic" if ("italic" in lower_stem or "oblique" in lower_stem) else "normal"

    weight = 400
    # Scan suffix / stem tokens for explicit weights (compound names ordered before simple ones)
    for token, w_val in _WEIGHT_MAP:
        if re.search(rf"(?:^|[-_\s]|(?<=[a-z0-9])){token}(?:italic|oblique|[-_\s]|$)", lower_stem):
            weight = w_val
            break
    else:
        num_match = re.search(r"(?:^|[-_\s])([1-9]00)(?:italic|oblique|[-_\s]|$)", lower_stem)
        if num_match:
            weight = int(num_match.group(1))

    # Iteratively strip trailing weight/style suffixes to get the shared base family name
    base = stem
    while True:
        stripped = _VARIANT_TOKEN_RE.sub("", base).rstrip("-_ ")
        if not stripped or stripped == base:
            break
        base = stripped

    label = _humanize_family_name(base if base else stem)
    family_slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "font"
    css_ident = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_") or "Font"

    return {
        "id": f"custom:{family_slug}",
        "label": label,
        "css_family": f"HKCustom_{css_ident}",
        "weight": weight,
        "style": style,
    }


def scan_custom_fonts(fonts_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Scans CUSTOM_FONTS_DIR (read-only) and groups valid font files by family."""
    target = Path(fonts_dir if fonts_dir is not None else config.CUSTOM_FONTS_DIR)
    if not target.is_dir():
        return []

    families: dict[str, dict[str, Any]] = {}
    variant_best: dict[tuple[str, int, str], tuple[int, dict[str, Any]]] = {}

    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        ext = entry.suffix.lower()
        fmt_info = ALLOWED_FONT_EXTS.get(ext)
        if not fmt_info:
            continue

        css_format, _mime_type, priority = fmt_info
        meta = parse_font_filename(entry.name)
        fam_id = meta["id"]
        if fam_id not in families:
            families[fam_id] = {
                "id": fam_id,
                "label": meta["label"],
                "css_family": meta["css_family"],
                "faces": [],
            }

        face = {
            "filename": entry.name,
            "url": f"/fonts/{quote(entry.name)}",
            "format": css_format,
            "weight": meta["weight"],
            "style": meta["style"],
        }
        vkey = (fam_id, meta["weight"], meta["style"])
        prev = variant_best.get(vkey)
        if prev is None or priority > prev[0]:
            variant_best[vkey] = (priority, face)

    for (fam_id, _w, _s), (_prio, face) in variant_best.items():
        families[fam_id]["faces"].append(face)

    result = list(families.values())
    for fam in result:
        fam["faces"].sort(
            key=lambda f: (0 if f["style"] == "normal" else 1, f["weight"], f["filename"].lower())
        )
    result.sort(key=lambda fam: fam["label"].lower())
    return result


def _resolve_custom_font_file(filename: str) -> tuple[Path, str] | None:
    """Validate and resolve a safe custom font file path inside CUSTOM_FONTS_DIR."""
    if (
        not filename
        or filename.startswith(".")
        or "/" in filename
        or "\\" in filename
        or ".." in filename
        or "\x00" in filename
    ):
        return None

    ext = Path(filename).suffix.lower()
    fmt_info = ALLOWED_FONT_EXTS.get(ext)
    if not fmt_info:
        return None

    _css_format, mime_type, _priority = fmt_info
    root = Path(config.CUSTOM_FONTS_DIR).resolve()
    try:
        candidate = (root / filename).resolve()
    except OSError:
        return None

    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate, mime_type


@router.get("/api/fonts")
async def list_custom_fonts():
    """Returns discovered custom font families from CUSTOM_FONTS_DIR."""
    fonts = await anyio.to_thread.run_sync(scan_custom_fonts)
    return JSONResponse(
        content={"folder": "custom_fonts", "fonts": fonts},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/fonts/{filename}")
async def serve_custom_font(filename: str):
    """Safely serves a font file from CUSTOM_FONTS_DIR."""
    resolved = await anyio.to_thread.run_sync(_resolve_custom_font_file, filename)
    if not resolved:
        raise HTTPException(status_code=404, detail="Font not found")
    candidate, mime_type = resolved

    return FileResponse(
        candidate,
        media_type=mime_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
