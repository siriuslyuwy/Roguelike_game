from __future__ import annotations

import locale
import os
from typing import Optional

_LANG: Optional[str] = None


class Translatable:
    def __init__(self, zh: str, en: Optional[str] = None):
        self.zh = zh
        self.en = en or ""

    def _pick(self) -> str:
        if get_lang() == "en" and self.en:
            return self.en
        return self.zh

    def __str__(self) -> str:
        return self._pick()

    def __repr__(self) -> str:
        return self._pick()

    def __format__(self, format_spec: str) -> str:
        return format(self._pick(), format_spec)


def _normalize_lang(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    raw = raw.replace("-", "_")
    return raw.lower()


def detect_lang() -> str:
    """Detect preferred language from env/locale. Returns 'zh' or 'en'."""
    for key in ("SEVENLINES_LANG", "LANGUAGE", "LC_ALL", "LANG"):
        raw = os.environ.get(key, "")
        norm = _normalize_lang(raw)
        if norm.startswith("zh"):
            return "zh"
        if norm.startswith("en"):
            return "en"
    try:
        loc = locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    norm = _normalize_lang(loc)
    if norm.startswith("zh"):
        return "zh"
    if norm.startswith("en"):
        return "en"
    return "zh"


def get_lang() -> str:
    global _LANG
    if not _LANG:
        _LANG = detect_lang()
    return _LANG


def set_lang(lang: str) -> None:
    """Manually set language to 'zh' or 'en'."""
    global _LANG
    lang = (lang or "").strip().lower()
    _LANG = "en" if lang.startswith("en") else "zh"


def tr(zh: str, en: Optional[str] = None) -> Translatable:
    """Create a translatable string that resolves by current language."""
    return Translatable(zh, en)
