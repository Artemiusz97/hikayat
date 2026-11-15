from __future__ import annotations

"""Venue-aware NPC activity tags, D7 context swaps, F1 telltale gating, and join-activity seeds."""

import hashlib
import re
from typing import Any, Mapping

from mechanics.social.anomalous_npc_tags import (
    TAG_ANOMALY_ENTITY,
    TAG_FOLKLORE_VILLAGER,
    TAG_SPECIAL_AGENT,
    classify_anomalous_npc_tag,
)

# Normalized internal activity keys mapped to 5-language display labels.
_ACTIVITY_LOCALES: dict[str, dict[str, str]] = {
    "studying": {"en": "Studying", "pl": "Uczy się", "ms": "Belajar", "de": "Lernt", "zh": "学习中"},
    "taking_notes": {"en": "Taking Notes", "pl": "Robi notatki", "ms": "Mencatat Nota", "de": "Macht Notizen", "zh": "做笔记"},
    "lecturing": {"en": "Lecturing", "pl": "Prowadzi wykład", "ms": "Mengajar", "de": "Hält Vortrag", "zh": "讲课中"},
    "grading": {"en": "Grading Papers", "pl": "Sprawdza prace", "ms": "Menyemak Tugasan", "de": "Korrigiert Arbeiten", "zh": "批改作业"},
    "reading": {"en": "Reading", "pl": "Czyta", "ms": "Membaca", "de": "Liest", "zh": "阅读中"},
    "researching": {"en": "Researching", "pl": "Szuka informacji", "ms": "Menyelidik", "de": "Recherchiert", "zh": "查阅资料"},
    "sparring": {"en": "Training", "pl": "Trenuje", "ms": "Berlatih", "de": "Trainiert", "zh": "训练中"},
    "stretching": {"en": "Warming Up", "pl": "Rozgrzewa się", "ms": "Memanaskan Badan", "de": "Wärmt sich auf", "zh": "热身中"},
    "sketching": {"en": "Sketching", "pl": "Szkicuje", "ms": "Melakar", "de": "Skizziert", "zh": "素描中"},
    "rehearsing": {"en": "Practicing", "pl": "Ćwiczy", "ms": "Berlatih", "de": "Probt", "zh": "排练中"},
    "eating": {"en": "Eating", "pl": "Je posiłek", "ms": "Sedang Makan", "de": "Isst", "zh": "用餐中"},
    "coffee_break": {"en": "Having a Drink", "pl": "Pije napój", "ms": "Minum", "de": "Trinkt etwas", "zh": "小酌休息"},
    "browsing_phone": {"en": "Checking Phone", "pl": "Sprawdza telefon", "ms": "Melihat Telefon", "de": "Schaut aufs Handy", "zh": "看手机"},
    "gazing_out": {"en": "Looking at the Sky", "pl": "Patrzy w dal", "ms": "Meninjau Pemandangan", "de": "Blickt hinaus", "zh": "远眺"},
    "tending_patients": {"en": "Tending Patients", "pl": "Opiekuje się chorymi", "ms": "Merawat Pesakit", "de": "Versorgt Patienten", "zh": "照料伤患"},
    "patrolling": {"en": "On Patrol", "pl": "Patroluje", "ms": "Meronda", "de": "Patrouilliert", "zh": "巡逻中"},
    "tending_bar": {"en": "Tending Counter", "pl": "Obsługuje ladę", "ms": "Menjaga Kaunter", "de": "Bedient den Tresen", "zh": "照看柜台"},
    "tending_stall": {"en": "Minding Stall", "pl": "Pilnuje straganu", "ms": "Menjaga Gerai", "de": "Führt den Stand", "zh": "看守摊位"},
    "praying": {"en": "Praying", "pl": "Modli się", "ms": "Berdoa", "de": "Betet", "zh": "祈祷中"},
    "brewing": {"en": "Brewing", "pl": "Warzy mikstury", "ms": "Membancuh Ramuan", "de": "Braut", "zh": "调配中"},
    "hacking": {"en": "Coding at Terminal", "pl": "Pracuje przy terminalu", "ms": "Menggodam Terminal", "de": "Am Terminal", "zh": "终端操作"},
    "monitoring": {"en": "Monitoring Sensors", "pl": "Monitoruje odczyty", "ms": "Memantau Pengesan", "de": "Überwacht Sensoren", "zh": "监控读数"},
    "tinkering": {"en": "Tinkering", "pl": "Majsterkuje", "ms": "Membaiki Peralatan", "de": "Tüftelt", "zh": "修理器械"},
    "cooking": {"en": "Cooking", "pl": "Gotuje", "ms": "Memasak", "de": "Kocht", "zh": "烹饪中"},
    "resting": {"en": "Relaxing", "pl": "Odpoczywa", "ms": "Berehat", "de": "Ruht sich aus", "zh": "休息中"},
    "hanging_out": {"en": "Hanging Out", "pl": "Spędza czas", "ms": "Melepak", "de": "Verbringt Zeit", "zh": "闲聊聚会"},
    "chatting": {"en": "Chatting", "pl": "Rozmawia", "ms": "Berbual", "de": "Plaudert", "zh": "交谈中"},
    "talking": {"en": "Talking", "pl": "Rozmawia", "ms": "Bercakap", "de": "Spricht", "zh": "交谈中"},
    "packing_up": {"en": "Packing Up", "pl": "Pakuje rzeczy", "ms": "Mengemas Barang", "de": "Packt ein", "zh": "收拾物品"},
    "waiting_for_you": {"en": "Waiting for You", "pl": "Czeka na ciebie", "ms": "Menunggu Anda", "de": "Wartet auf dich", "zh": "在等你"},
    "checking_time": {"en": "Checking Time", "pl": "Sprawdza czas", "ms": "Melihat Masa", "de": "Schaut auf die Uhr", "zh": "查看时间"},
    "telltale_unblinking": {"en": "Unblinking Watch", "pl": "Patrzy bez mrugnięcia", "ms": "Renungan Kaku", "de": "Starrt reglos", "zh": "一动不动地凝视"},
    "telltale_earpiece": {"en": "Checking Earpiece", "pl": "Poprawia słuchawkę", "ms": "Memeriksa Alat Telinga", "de": "Prüft Ohrhörer", "zh": "轻触隐蔽耳麦"},
    "telltale_shadow": {"en": "Shadow Out of Step", "pl": "Nieswój cień", "ms": "Bayang Ganjil", "de": "Seltsamer Schatten", "zh": "影子微微错位"},
}

_DEEP_FOCUS_KEYS = frozenset({
    "studying", "taking_notes", "lecturing", "grading", "reading",
    "researching", "sparring", "sketching", "rehearsing",
    "tending_patients", "brewing", "hacking", "monitoring", "tinkering", "praying",
})

# Stat + bounded DC (5..8) + SDXL pose tags per activity key.
_ACTIVITY_SPECS: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "studying": ("INT", 6, ("sitting at desk", "open textbook", "focused expression")),
    "taking_notes": ("INT", 5, ("sitting", "holding pen", "writing in notebook")),
    "lecturing": ("INT", 7, ("standing at podium", "gesturing", "holding chalk")),
    "grading": ("INT", 7, ("sitting at desk", "stack of papers", "red pen")),
    "reading": ("INT", 5, ("holding open book", "quiet posture")),
    "researching": ("PER", 6, ("leaning over table", "examining documents")),
    "sparring": ("STR", 7, ("athletic stance", "towel around neck", "training")),
    "stretching": ("AGI", 5, ("stretching arms", "sportswear", "warm up")),
    "sketching": ("PER", 5, ("holding sketchbook", "pencil in hand")),
    "rehearsing": ("CHA", 6, ("practicing posture", "focused expression")),
    "eating": ("CHA", 5, ("sitting at table", "meal tray")),
    "coffee_break": ("CHA", 5, ("holding mug", "relaxed posture")),
    "browsing_phone": ("PER", 5, ("looking at smartphone", "relaxed leaning")),
    "gazing_out": ("PER", 5, ("leaning on railing", "wind in hair")),
    "tending_patients": ("INT", 7, ("checking medical chart", "attending desk")),
    "patrolling": ("PER", 7, ("standing alert", "scanning area")),
    "tending_bar": ("CHA", 6, ("behind counter", "wiping glass")),
    "tending_stall": ("CHA", 5, ("behind merchant stall", "arranging wares")),
    "praying": ("PER", 6, ("hands clasped", "serene expression")),
    "brewing": ("INT", 7, ("tending vials", "careful pouring")),
    "hacking": ("INT", 7, ("typing at glowing console", "focused gaze")),
    "monitoring": ("PER", 7, ("watching telemetry screens", "standing at console")),
    "tinkering": ("END", 6, ("holding wrench", "workbench tools")),
    "cooking": ("END", 5, ("at kitchen counter", "preparing food")),
    "resting": ("CHA", 5, ("lounging comfortably", "relaxed shoulders")),
    "hanging_out": ("CHA", 5, ("casual stance", "warm smile")),
    "chatting": ("CHA", 5, ("animated conversation", "facing companion")),
    "talking": ("CHA", 5, ("engaged in conversation", "eye contact")),
    "packing_up": ("AGI", 5, ("gathering bag", "putting away items")),
    "waiting_for_you": ("CHA", 5, ("looking toward entrance", "expectant smile")),
    "checking_time": ("PER", 6, ("glancing at watch", "tapping foot")),
    "telltale_unblinking": ("PER", 8, ("unnaturally still posture", "intense stare")),
    "telltale_earpiece": ("PER", 8, ("hand near ear", "scanning room calmly")),
    "telltale_shadow": ("PER", 8, ("dim lighting", "subtle uncanny stillness")),
}

_VENUE_CATALOGS: dict[str, dict[str, tuple[str, ...]]] = {
    "campus": {
        "classroom": ("studying", "taking_notes", "reading"),
        "library": ("reading", "researching", "studying"),
        "gym": ("sparring", "stretching", "resting"),
        "club_room": ("rehearsing", "sketching", "hanging_out"),
        "rooftop": ("gazing_out", "resting", "browsing_phone"),
        "cafeteria": ("eating", "coffee_break", "chatting"),
        "infirmary": ("resting", "reading", "tending_patients"),
        "residence": ("cooking", "resting", "hanging_out", "studying"),
        "general": ("chatting", "browsing_phone", "studying"),
    },
    "fantasy": {
        "tavern": ("coffee_break", "eating", "chatting"),
        "guildhall": ("researching", "sparring", "chatting"),
        "shrine": ("praying", "reading", "resting"),
        "barracks": ("sparring", "patrolling", "tinkering"),
        "market": ("tending_stall", "chatting", "browsing_phone"),
        "alchemy_lab": ("brewing", "researching", "reading"),
        "infirmary": ("tending_patients", "brewing", "resting"),
        "residence": ("cooking", "resting", "reading", "hanging_out"),
        "general": ("patrolling", "chatting", "resting"),
    },
    "cyberpunk": {
        "nightclub": ("coffee_break", "hanging_out", "chatting"),
        "clinic": ("tending_patients", "monitoring", "tinkering"),
        "net_den": ("hacking", "monitoring", "coffee_break"),
        "market": ("tending_stall", "tinkering", "browsing_phone"),
        "residence": ("hacking", "cooking", "resting", "hanging_out"),
        "general": ("browsing_phone", "patrolling", "chatting"),
    },
    "sci_fi": {
        "lab": ("monitoring", "researching", "hacking"),
        "mess_deck": ("eating", "coffee_break", "chatting"),
        "bridge": ("monitoring", "patrolling", "researching"),
        "hangar": ("tinkering", "monitoring", "stretching"),
        "clinic": ("tending_patients", "monitoring", "resting"),
        "residence": ("resting", "reading", "hanging_out"),
        "general": ("monitoring", "patrolling", "resting"),
    },
    "anomalous": {
        "bureau": ("researching", "monitoring", "coffee_break"),
        "containment": ("monitoring", "patrolling", "tinkering"),
        "investigation_hub": ("researching", "hacking", "chatting"),
        "infirmary": ("tending_patients", "resting", "monitoring"),
        "residence": ("cooking", "resting", "researching", "hanging_out"),
        "general": ("patrolling", "researching", "monitoring"),
    },
    "folklore": {
        "shrine": ("praying", "tending_stall", "resting"),
        "tavern": ("coffee_break", "eating", "chatting"),
        "market": ("tending_stall", "chatting", "sketching"),
        "residence": ("cooking", "resting", "hanging_out"),
        "general": ("praying", "chatting", "tending_stall"),
    },
}

TELLTALE_PER_DC = 13


def _norm_lang(lang: str) -> str:
    code = str(lang or "en").strip().lower()[:2]
    return code if code in ("en", "pl", "ms", "de", "zh") else "en"


def localize_activity_key(activity_key: str, lang: str = "en") -> str:
    """Returns the localized display label for an internal activity key."""
    key = str(activity_key or "").strip().lower()
    if not key:
        return ""
    entry = _ACTIVITY_LOCALES.get(key)
    if not entry:
        return key.replace("_", " ").title()
    l_code = _norm_lang(lang)
    return entry.get(l_code) or entry.get("en") or ""


def _resolve_genre_bucket(scen_key: str) -> str:
    sk = str(scen_key or "").strip().lower()
    if "high_school" in sk or "academy" in sk or "campus" in sk:
        return "campus"
    if "cyberpunk" in sk:
        return "cyberpunk"
    if "sci_fi" in sk or "space" in sk:
        return "sci_fi"
    if "anomalous" in sk or "bureau" in sk:
        return "anomalous"
    if "folklore" in sk:
        return "folklore"
    if "slice_of_life" in sk:
        return "campus"
    return "fantasy"


_RESIDENCE_RE = re.compile(
    r"(?<![a-z])(?:residence|home|apartment|bedroom|dorm|living_room|kitchen|cottage)(?![a-z])",
    re.IGNORECASE,
)


def _resolve_venue_key(location: str, node_type: str) -> str:
    probe = f"{node_type} {location}".lower()
    if any(k in probe for k in ("classroom", "homeroom", "lecture", "class 1-", "class 2-", "class 3-", "class 4-")):
        return "classroom"
    if _RESIDENCE_RE.search(probe):
        return "residence"
    if any(k in probe for k in ("library", "archive", "bookstore", "study hall")):
        return "library"
    if any(k in probe for k in ("gym", "track", "field", "pool", "dojo", "court", "training")):
        return "gym"
    if any(k in probe for k in ("club", "art room", "music room", "student council")):
        return "club_room"
    if any(k in probe for k in ("rooftop", "balcony", "overlook", "terrace")):
        return "rooftop"
    if any(k in probe for k in ("cafeteria", "dining", "mess", "canteen", "cafe", "bakery")):
        return "cafeteria"
    if any(k in probe for k in ("infirmary", "clinic", "hospital", "medical", "triage")):
        return "infirmary"
    if any(k in probe for k in ("tavern", "inn", "pub", "bar", "lounge", "nightclub")):
        return "tavern"
    if any(k in probe for k in ("guild", "hall")):
        return "guildhall"
    if any(k in probe for k in ("shrine", "temple", "chapel", "sanctuary")):
        return "shrine"
    if any(k in probe for k in ("barrack", "gate", "guard", "watch")):
        return "barracks"
    if any(k in probe for k in ("market", "shop", "bazaar", "mall", "stall", "commercial")):
        return "market"
    if any(k in probe for k in ("alchemy", "apothecary", "potion")):
        return "alchemy_lab"
    if any(k in probe for k in ("net", "server", "cyber", "terminal")):
        return "net_den"
    if any(k in probe for k in ("containment", "vault", "rift", "anomaly")):
        return "containment"
    if any(k in probe for k in ("bureau", "office", "headquarters", "command", "bridge")):
        return "bureau"
    if any(k in probe for k in ("lab", "workshop", "forge", "hangar")):
        return "lab"
    return "general"


def _npc_role_probe(npc: Mapping[str, Any]) -> str:
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), Mapping) else {}
    return " ".join(
        str(x or "").lower()
        for x in (
            npc.get("role"),
            npc.get("occupation"),
            npc.get("archetype"),
            basic.get("role"),
            basic.get("occupation"),
            npc.get("faction"),
        )
    )


def _select_role_or_venue_key(
    npc: Mapping[str, Any],
    *,
    genre: str,
    venue: str,
    time_block: str,
    paired_with: str,
    session_id: int,
    day: int,
) -> str:
    role_probe = _npc_role_probe(npc)
    if venue == "residence":
        choices = _VENUE_CATALOGS[genre].get("residence", ("cooking", "resting", "hanging_out"))
    elif any(k in role_probe for k in ("teacher", "professor", "instructor")) and venue == "classroom":
        return "lecturing" if time_block in ("morning", "afternoon") else "grading"
    elif any(k in role_probe for k in ("nurse", "doctor", "medic", "healer")) and venue in ("infirmary", "clinic"):
        return "tending_patients"
    elif any(k in role_probe for k in ("librarian", "archivist")) and venue == "library":
        return "researching"
    elif any(k in role_probe for k in ("bartender", "barkeep", "innkeeper", "barista")) and venue in ("tavern", "nightclub", "cafeteria"):
        return "tending_bar"
    elif any(k in role_probe for k in ("merchant", "shopkeeper", "vendor", "clerk")) and venue == "market":
        return "tending_stall"
    elif any(k in role_probe for k in ("guard", "watch", "security", "officer")) and time_block != "night":
        return "patrolling"
    elif paired_with:
        return "chatting"
    else:
        cat = _VENUE_CATALOGS.get(genre, _VENUE_CATALOGS["fantasy"])
        if genre in ("cyberpunk",) and venue == "tavern":
            venue = "nightclub"
        elif genre in ("sci_fi",) and venue == "cafeteria":
            venue = "mess_deck"
        elif genre in ("sci_fi",) and venue == "bureau":
            venue = "bridge"
        elif genre in ("anomalous",) and venue == "library":
            venue = "bureau"
        choices = cat.get(venue) or cat.get("general") or ("chatting", "resting")

    npc_ident = str(npc.get("npc_id") or npc.get("person_key") or npc.get("name") or "npc").strip().lower()
    digest = hashlib.sha256(f"{session_id}:{day}:{time_block}:{venue}:{npc_ident}".encode("utf-8")).hexdigest()
    return choices[int(digest[:8], 16) % len(choices)]


def _detect_disguised_telltale_key(npc: Mapping[str, Any]) -> str:
    """Returns a telltale activity key ONLY when the NPC actually holds a hidden disguise/anomaly/agent nature."""
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), Mapping) else {}
    flags = " ".join(
        str(x or "").lower()
        for x in (
            npc.get("secret"),
            npc.get("hidden_trait"),
            basic.get("secret"),
            basic.get("disguise"),
            basic.get("anomalous_tag"),
        )
    )
    tag = classify_anomalous_npc_tag(npc)
    is_disguised = bool(
        npc.get("is_disguised")
        or basic.get("is_disguised")
        or any(k in flags for k in ("stalker", "undercover", "impostor", "mimic", "glamour", "disguised", "shapeshifter"))
    )
    if tag == TAG_SPECIAL_AGENT and (is_disguised or "undercover" in _npc_role_probe(npc) or "civilian" in flags):
        return "telltale_earpiece"
    if tag == TAG_ANOMALY_ENTITY and is_disguised:
        return "telltale_unblinking"
    if tag == TAG_FOLKLORE_VILLAGER and ("glamour" in flags or is_disguised):
        return "telltale_shadow"
    if "stalker" in flags:
        return "telltale_unblinking"
    return ""


def resolve_actor_activity_bundle(
    npc: Mapping[str, Any],
    *,
    location: str = "",
    node_type: str = "",
    scen_key: str = "fantasy",
    time_block: str = "afternoon",
    stage_role: str = "room_bystander",
    is_dialogue_partner: bool = False,
    is_joined_activity: bool = False,
    is_combat: bool = False,
    is_erotic: bool = False,
    is_stealth: bool = False,
    paired_with: str = "",
    rendezvous_state: str = "",
    minutes_to_bell: int = 60,
    max_party_per: int = 10,
    lang: str = "en",
    session_id: int = 0,
    day: int = 1,
) -> dict[str, Any]:
    """Computes server-evaluated actor activity tag, focus DC modifier, SDXL poses, and F1 telltale gating."""
    if is_combat or is_erotic:
        return {
            "activity_key": "",
            "activity_tag": "",
            "secondary_tag": "",
            "focus_dc_mod": 0,
            "sdxl_pose_tags": (),
            "join_activity_seed": None,
            "telltale_spotted": False,
        }

    genre = _resolve_genre_bucket(scen_key)
    venue = _resolve_venue_key(location, node_type)
    l_code = _norm_lang(lang)

    # D10 rendezvous overrides background idling.
    rv = str(rendezvous_state or "").strip().lower()
    if rv == "waiting":
        base_key = "waiting_for_you"
    elif rv in ("checking_time", "late"):
        base_key = "checking_time"
    else:
        base_key = _select_role_or_venue_key(
            npc,
            genre=genre,
            venue=venue,
            time_block=str(time_block or "afternoon").lower(),
            paired_with=str(paired_with or ""),
            session_id=int(session_id or 0),
            day=int(day or 1),
        )

    # D7: Bell countdown swaps schoolwork/idling to Packing Up (< 15 min) when not talking.
    is_school_hours = genre == "campus" and venue != "residence" and str(time_block or "").lower() in ("morning", "lunch", "afternoon")
    if is_school_hours and int(minutes_to_bell) < 15 and not is_dialogue_partner and not rv:
        base_key = "packing_up"

    # F1: Strict server-side PER telltale check (NEVER leak telltale_tag / cover_tag keys).
    telltale_key = _detect_disguised_telltale_key(npc)
    telltale_spotted = bool(telltale_key and int(max_party_per) >= TELLTALE_PER_DC)
    effective_key = telltale_key if telltale_spotted else base_key

    # D7: Dialogue swaps cleanly so NPCs aren't listed as "Studying" mid-conversation unless joined.
    if is_dialogue_partner:
        talk_lbl = localize_activity_key("talking", l_code)
        base_lbl = localize_activity_key(effective_key, l_code)
        if is_joined_activity and effective_key not in ("talking", "chatting"):
            display_tag = f"{talk_lbl} • {base_lbl}"
            secondary_tag = base_lbl
        else:
            display_tag = talk_lbl
            secondary_tag = ""
        pose_key = effective_key if is_joined_activity else "talking"
    else:
        display_tag = localize_activity_key(effective_key, l_code)
        secondary_tag = ""
        pose_key = effective_key

    stat, dc, poses = _ACTIVITY_SPECS.get(pose_key, ("CHA", 6, ("casual posture",)))
    bounded_dc = max(5, min(8, int(dc)))
    focus_dc_mod = 1 if (not is_dialogue_partner and effective_key in _DEEP_FOCUS_KEYS) else 0

    join_seed: dict[str, Any] | None = None
    if not is_stealth and not is_joined_activity and stage_role in (
        "room_bystander",
        "room_companion",
        "dialogue_partner",
        "ambient_patron",
    ):
        join_seed = {
            "stat": stat,
            "dc": bounded_dc,
            "activity_key": effective_key,
            "activity_tag": localize_activity_key(effective_key, l_code),
        }

    return {
        "activity_key": "talking" if (is_dialogue_partner and not is_joined_activity) else effective_key,
        "activity_tag": display_tag,
        "secondary_tag": secondary_tag,
        "focus_dc_mod": focus_dc_mod,
        "sdxl_pose_tags": poses,
        "join_activity_seed": join_seed,
        "telltale_spotted": telltale_spotted,
    }


def get_activity_situational_dc_mod(
    npc: Mapping[str, Any],
    intent: str,
    action_text: str = "",
) -> int:
    """Returns +1 when interrupting deep focus/work, -1 when joining/aligning, or 0 neutral."""
    act_key = str(npc.get("activity_key") or "").strip().lower()
    in_norm = str(intent or "").strip().lower()
    txt_low = str(action_text or "").strip().lower()

    if in_norm == "join_activity" or any(
        tok in txt_low for tok in ("join ", "study together", "help with", "train together", "sit beside", "cook together", "share a drink")
    ):
        return -1

    if act_key in _DEEP_FOCUS_KEYS and in_norm in ("dialogue_init", "disclosure_inquiry", "social_invite", "romantic_confession", "affection_touch"):
        return 1

    return 0
