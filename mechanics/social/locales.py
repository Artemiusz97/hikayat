from __future__ import annotations

"""5-language localization catalog for Hikayat's Dynamic Social Engine (en, pl, ms, de, zh)."""

from typing import Any

SUPPORTED_SOCIAL_LOCALES: tuple[str, ...] = ("en", "pl", "ms", "de", "zh")

MOOD_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "Engaged": "Engaged",
        "Guarded": "Guarded",
        "Drained": "Drained",
        "Upset": "Upset",
    },
    "pl": {
        "Engaged": "Zaangażowany",
        "Guarded": "Zdystansowany",
        "Drained": "Wyczerpany",
        "Upset": "Urażony",
    },
    "ms": {
        "Engaged": "Berminat",
        "Guarded": "Berhati-hati",
        "Drained": "Lesu",
        "Upset": "Tersinggung",
    },
    "de": {
        "Engaged": "Aufgeschlossen",
        "Guarded": "Reserviert",
        "Drained": "Erschöpft",
        "Upset": "Verärgert",
    },
    "zh": {
        "Engaged": "投入",
        "Guarded": "戒备",
        "Drained": "疲惫",
        "Upset": "不悦",
    },
}

PILL_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "trait_unlocked": ("Unlocked Trait", "Unlocked Trait: {detail}"),
        "like_unlocked": ("Unlocked Like", "Unlocked Like: {detail}"),
        "dislike_unlocked": ("Unlocked Dislike", "Unlocked Dislike: {detail}"),
        "schedule_unlocked": ("Unlocked Routine", "Unlocked Routine: {detail}"),
        "intimate_unlocked": ("Unlocked Intimate Detail", "Unlocked Intimate Detail: {detail}"),
        "bond_settling": ("Bond Settling Today", "Bond Settling ({detail})"),
        "topic_locked": ("Topic Cooling Down", "Topic Cooling Down: {detail}"),
        "clear_the_air": ("Tension — Clear the Air", "Clear the Air: {detail}"),
        "rival_sparked": ("Rivalry Sparked", "Rivalry Sparked: {detail}"),
        "cold_shoulder": ("Cold Shoulder", "Cold Shoulder: {detail}"),
        "focus_on_road": ("Focused on the Road", "Focused on the Road: {detail}"),
    },
    "pl": {
        "trait_unlocked": ("Odkryto cechę", "Odkryto cechę: {detail}"),
        "like_unlocked": ("Odkryto upodobanie", "Odkryto upodobanie: {detail}"),
        "dislike_unlocked": ("Odkryto niechęć", "Odkryto niechęć: {detail}"),
        "schedule_unlocked": ("Odkryto plan dnia", "Odkryto plan dnia: {detail}"),
        "intimate_unlocked": ("Odkryto sekret intymny", "Odkryto sekret intymny: {detail}"),
        "bond_settling": ("Więź utrwala się na dziś", "Więź utrwala się ({detail})"),
        "topic_locked": ("Temat wyczerpany", "Temat wyczerpany: {detail}"),
        "clear_the_air": ("Napięcie — wyjaśnij sytuację", "Wyjaśnij sytuację: {detail}"),
        "rival_sparked": ("Iskra rywalizacji", "Iskra rywalizacji: {detail}"),
        "cold_shoulder": ("Chłodny dystans", "Chłodny dystans: {detail}"),
        "focus_on_road": ("Skupienie na drodze", "Skupienie na drodze: {detail}"),
    },
    "ms": {
        "trait_unlocked": ("Sifat Ditemui", "Sifat Ditemui: {detail}"),
        "like_unlocked": ("Kegemaran Ditemui", "Kegemaran Ditemui: {detail}"),
        "dislike_unlocked": ("Pantang Ditemui", "Pantang Ditemui: {detail}"),
        "schedule_unlocked": ("Jadual Ditemui", "Jadual Ditemui: {detail}"),
        "intimate_unlocked": ("Butiran Peribadi Ditemui", "Butiran Peribadi Ditemui: {detail}"),
        "bond_settling": ("Ikatan Sedang Serasi", "Ikatan Sedang Serasi ({detail})"),
        "topic_locked": ("Topik Ditangguhkan", "Topik Ditangguhkan: {detail}"),
        "clear_the_air": ("Ketegangan — Jernihkan Suasana", "Jernihkan Suasana: {detail}"),
        "rival_sparked": ("Persaingan Tercetus", "Persaingan Tercetus: {detail}"),
        "cold_shoulder": ("Layanan Dingin", "Layanan Dingin: {detail}"),
        "focus_on_road": ("Fokus Pada Perjalanan", "Fokus Pada Perjalanan: {detail}"),
    },
    "de": {
        "trait_unlocked": ("Eigenschaft entdeckt", "Eigenschaft entdeckt: {detail}"),
        "like_unlocked": ("Vorliebe entdeckt", "Vorliebe entdeckt: {detail}"),
        "dislike_unlocked": ("Abneigung entdeckt", "Abneigung entdeckt: {detail}"),
        "schedule_unlocked": ("Tagesablauf entdeckt", "Tagesablauf entdeckt: {detail}"),
        "intimate_unlocked": ("Intimes Detail entdeckt", "Intimes Detail entdeckt: {detail}"),
        "bond_settling": ("Bindung festigt sich heute", "Bindung festigt sich ({detail})"),
        "topic_locked": ("Thema vorerst erschöpft", "Thema erschöpft: {detail}"),
        "clear_the_air": ("Spannung — Aussprache nötig", "Aussprache nötig: {detail}"),
        "rival_sparked": ("Rivalität entfacht", "Rivalität entfacht: {detail}"),
        "cold_shoulder": ("Kalte Schulter", "Kalte Schulter: {detail}"),
        "focus_on_road": ("Fokus auf den Weg", "Fokus auf den Weg: {detail}"),
    },
    "zh": {
        "trait_unlocked": ("解锁特质", "解锁特质：{detail}"),
        "like_unlocked": ("解锁喜好", "解锁喜好：{detail}"),
        "dislike_unlocked": ("解锁厌恶", "解锁厌恶：{detail}"),
        "schedule_unlocked": ("解锁作息", "解锁作息：{detail}"),
        "intimate_unlocked": ("解锁私密档案", "解锁私密档案：{detail}"),
        "bond_settling": ("今日羁绊沉淀中", "羁绊沉淀中（{detail}）"),
        "topic_locked": ("话题暂时冷却", "话题冷却：{detail}"),
        "clear_the_air": ("气氛紧绷——需要化解心结", "化解心结：{detail}"),
        "rival_sparked": ("激起竞争之心", "激起竞争：{detail}"),
        "cold_shoulder": ("冷淡对待", "冷淡对待：{detail}"),
        "focus_on_road": ("专心赶路", "专心赶路：{detail}"),
    },
}

MASKED_PLACEHOLDERS: dict[str, dict[str, str]] = {
    "en": {"slot": "???", "fact": "???", "schedule": "??? (Routine Unknown)", "intimate": "??? (Private)"},
    "pl": {"slot": "???", "fact": "???", "schedule": "??? (Plan nieznany)", "intimate": "??? (Prywatne)"},
    "ms": {"slot": "???", "fact": "???", "schedule": "??? (Jadual Belum Diketahui)", "intimate": "??? (Peribadi)"},
    "de": {"slot": "???", "fact": "???", "schedule": "??? (Ablauf unbekannt)", "intimate": "??? (Privat)"},
    "zh": {"slot": "???", "fact": "???", "schedule": "???（作息未知）", "intimate": "???（私密）"},
}


def normalize_social_lang(lang: str | None) -> str:
    code = str(lang or "en").strip().lower().split("-")[0].split("_")[0]
    return code if code in SUPPORTED_SOCIAL_LOCALES else "en"


def get_mood_label(mood: str, lang: str = "en") -> str:
    norm_lang = normalize_social_lang(lang)
    raw = str(mood or "Engaged").strip()
    canon = raw.title() if raw.lower() in ("engaged", "guarded", "drained", "upset") else "Engaged"
    return MOOD_LABELS.get(norm_lang, MOOD_LABELS["en"]).get(canon, canon)


def format_feedback_pill(pill_key: str, detail: str = "", lang: str = "en") -> str:
    norm_lang = normalize_social_lang(lang)
    key = str(pill_key or "").strip().lower()
    table = PILL_TEMPLATES.get(norm_lang, PILL_TEMPLATES["en"])
    short_tpl, detail_tpl = table.get(key) or PILL_TEMPLATES["en"].get(key) or (key.replace("_", " ").title(), "{detail}")
    clean_detail = str(detail or "").strip()
    if clean_detail:
        return detail_tpl.format(detail=clean_detail)
    return short_tpl


def get_masked_placeholder(category: str = "fact", lang: str = "en") -> str:
    norm_lang = normalize_social_lang(lang)
    cat = str(category or "fact").strip().lower()
    table = MASKED_PLACEHOLDERS.get(norm_lang, MASKED_PLACEHOLDERS["en"])
    return table.get(cat, "???")


def build_turn_feedback_pill_payload(
    pill_key: str,
    detail: str = "",
    lang: str = "en",
    tone: str = "neutral",
) -> dict[str, Any]:
    return {
        "key": str(pill_key or "").strip().lower(),
        "label": format_feedback_pill(pill_key, detail=detail, lang=lang),
        "detail": str(detail or "").strip(),
        "tone": str(tone or "neutral").strip(),
    }
