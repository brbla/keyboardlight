"""Minimal translation layer: Czech source strings, English dictionary in i18n_en.py.

Language: settings file (~/.config/keyboardlight/settings.json, key "language": "cs"/"en"),
otherwise the system locale (cs_* -> Czech, anything else -> English).
A language change takes effect after restarting the app.
"""
from __future__ import annotations

import json
import locale
import os

SETTINGS = os.path.expanduser('~/.config/keyboardlight/settings.json')
LANGUAGES = {'cs': 'Čeština', 'en': 'English'}


def _settings() -> dict:
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_setting(key: str, value) -> None:
    data = _settings()
    data[key] = value
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def detect_language() -> str:
    lang = os.environ.get('KEYBOARDLIGHT_LANG') or _settings().get('language')
    if lang in LANGUAGES:
        return lang
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        val = os.environ.get(var, '')
        if val:
            return 'cs' if val.lower().startswith(('cs', 'cz')) else 'en'
    loc = (locale.getlocale()[0] or '').lower()
    return 'cs' if loc.startswith('cs') else 'en'


LANG = detect_language()
_EN: dict[str, str] | None = None


def _(text: str) -> str:
    """Translate a Czech source string into the active language."""
    global _EN
    if LANG == 'cs':
        return text
    if _EN is None:
        from keyboardlight.i18n_en import EN
        _EN = EN
    return _EN.get(text, text)
