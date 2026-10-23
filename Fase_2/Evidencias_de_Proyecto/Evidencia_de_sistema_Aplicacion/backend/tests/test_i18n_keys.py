"""Tests: claves i18n en en.ts presentes en es.ts (locales principales)."""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MESSAGES = PROJECT_ROOT / "frontend" / "src" / "i18n" / "messages"


def _keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'^\s+"([^"]+)":', text, flags=re.MULTILINE))


def test_en_and_es_have_same_translation_keys():
    en = _keys(MESSAGES / "en.ts")
    es = _keys(MESSAGES / "es.ts")
    missing_in_es = en - es
    missing_in_en = es - en
    assert not missing_in_es, f"Faltan en es.ts: {sorted(missing_in_es)[:10]}"
    assert not missing_in_en, f"Huérfanas en es.ts: {sorted(missing_in_en)[:10]}"
